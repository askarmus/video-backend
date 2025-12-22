import re
import json
import shutil
import tempfile
import subprocess
import os
from pathlib import Path

# Config / Constants
FREEZE_NOISE = 0.001
FREEZE_MIN_D = 0.50
SILENCE_DB = -35
SILENCE_MIN_D = 0.50
PAD_BEFORE = 0.20
PAD_AFTER = 0.35
MIN_KEEP_SEG = 0.40
MIN_CUT_SEG = 0.50

class VideoService:
    def __init__(self):
        if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
            raise RuntimeError("ffmpeg/ffprobe not found. Install FFmpeg and add it to PATH.")

    def run_cmd(self, cmd):
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"Command failed:\n{' '.join(cmd)}\n\nSTDERR:\n{p.stderr[:4000]}")
        return p.stdout, p.stderr

    def get_duration(self, path):
        out, _ = self.run_cmd([
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", str(path)
        ])
        j = json.loads(out)
        # Use .get() to safely access nested keys and provide a default
        duration_str = j.get("format", {}).get("duration", "0")
        return float(duration_str)

    def parse_freezedetect(self, stderr_text):
        starts = []
        freezes = []
        for line in stderr_text.splitlines():
            m1 = re.search(r"freeze_start:\s*([0-9.]+)", line)
            if m1:
                starts.append(float(m1.group(1)))
            m2 = re.search(r"freeze_end:\s*([0-9.]+).*freeze_duration:\s*([0-9.]+)", line)
            if m2 and starts:
                end = float(m2.group(1))
                dur = float(m2.group(2))
                start = starts.pop(0)
                if dur >= FREEZE_MIN_D:
                    freezes.append((start, end))
        return freezes

    def parse_silencedetect(self, stderr_text):
        starts = []
        silences = []
        for line in stderr_text.splitlines():
            m1 = re.search(r"silence_start:\s*([0-9.]+)", line)
            if m1:
                starts.append(float(m1.group(1)))
            m2 = re.search(r"silence_end:\s*([0-9.]+).*silence_duration:\s*([0-9.]+)", line)
            if m2 and starts:
                end = float(m2.group(1))
                dur = float(m2.group(2))
                start = starts.pop(0)
                if dur >= SILENCE_MIN_D:
                    silences.append((start, end))
        return silences

    def merge_intervals(self, intervals, gap=0.05):
        if not intervals:
            return []
        intervals = sorted(intervals)
        merged = [list(intervals[0])]
        for s, e in intervals[1:]:
            if s <= merged[-1][1] + gap:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])
        return [(s, e) for s, e in merged]

    def invert_to_keep(self, cuts, duration):
        cuts = self.merge_intervals([(max(0.0, s), min(duration, e)) for s, e in cuts])
        keep = []
        cur = 0.0
        for s, e in cuts:
            if s > cur:
                keep.append((cur, s))
            cur = max(cur, e)
        if cur < duration:
            keep.append((cur, duration))
        return keep

    def apply_padding(self, cuts, duration):
        padded = []
        for s, e in cuts:
            ps = max(0.0, s - PAD_BEFORE)
            pe = min(duration, e + PAD_AFTER)
            if pe - ps >= MIN_CUT_SEG:
                padded.append((ps, pe))
        return self.merge_intervals(padded)

    def fast_trim(self, input_path, output_path):
        """
        Trims silence and freezes from a video file.
        """
        dur = self.get_duration(input_path)

        # 1) Detect freezes (visual dead)
        _, err_freeze = self.run_cmd([
            "ffmpeg", "-hide_banner", "-nostdin",
            "-i", str(input_path),
            "-vf", f"freezedetect=n={FREEZE_NOISE}:d={FREEZE_MIN_D}",
            "-an", "-f", "null", "-"
        ])
        freezes = self.merge_intervals(self.parse_freezedetect(err_freeze))

        # 2) Detect silences (audio dead)
        _, err_sil = self.run_cmd([
            "ffmpeg", "-hide_banner", "-nostdin",
            "-i", str(input_path),
            "-af", f"silencedetect=noise={SILENCE_DB}dB:d={SILENCE_MIN_D}",
            "-vn", "-f", "null", "-"
        ])
        silences = self.merge_intervals(self.parse_silencedetect(err_sil))

        # 3) Cut logic (here using silence as primary trigger, as in original script)
        dead = self.apply_padding(silences, dur)
        keep = self.invert_to_keep(dead, dur)

        # 4) Export
        self.export_segments(input_path, keep, output_path)
        
        return output_path

    def export_segments(self, input_path, keep, output_path):
        tmp = Path(tempfile.mkdtemp(prefix="trim_"))
        seg_files = []
        try:
            for idx, (s, e) in enumerate(keep):
                if e - s < MIN_KEEP_SEG:
                    continue
                seg = tmp / f"seg_{idx:04d}.mp4"
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", f"{s:.3f}", "-to", f"{e:.3f}",
                    "-i", str(input_path),
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                    "-c:a", "aac", "-b:a", "128k",
                    "-movflags", "+faststart",
                    str(seg)
                ]
                self.run_cmd(cmd)
                seg_files.append(seg)

            if not seg_files:
                raise RuntimeError("No segments left after trimming.")

            concat_list = tmp / "concat.txt"
            concat_list.write_text("\n".join([f"file '{f.as_posix()}'" for f in seg_files]), encoding="utf-8")

            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_list),
                "-c", "copy",
                str(output_path)
            ]
            self.run_cmd(cmd)
        finally:
            # Note: In production you might want to cleanup tmp, 
            # but sometimes it's useful for debugging
            pass
    
    def get_audio_duration(self, path):
        out, _ = self.run_cmd([
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", str(path)
        ])
        j = json.loads(out)
        return float(j["format"]["duration"])

    def cut_segment(self, input_path, start, duration, output_path):
        end = start + duration
        self.run_cmd([
            "ffmpeg", "-y",
            "-ss", f"{start:.3f}",
            "-to", f"{end:.3f}",
            "-i", str(input_path),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-an",
            str(output_path)
        ])

    def freeze_to_duration(self, input_path, target_duration, output_path):
        current = self.get_duration(input_path)
        if current >= target_duration:
            shutil.copy(input_path, output_path)
            return

        pad = target_duration - current

        self.run_cmd([
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-vf", f"tpad=stop_mode=clone:stop_duration={pad}",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-an",
            str(output_path)
        ])
    
    def attach_audio(self, video_path, audio_path, output_path):
        self.run_cmd([
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-map", "0:v",
        "-map", "1:a",
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        str(output_path)
    ])

    def concat_clips(self, clips, output_path):
        tmp = Path(tempfile.mkdtemp(prefix="final_concat_"))
        lst = tmp / "list.txt"
        lst.write_text("\n".join(
            [f"file '{Path(c).as_posix()}'" for c in clips]
        ), encoding="utf-8")

        self.run_cmd([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(lst),
            "-c", "copy",
            str(output_path)
        ])

    def assemble_steps(self, raw_video, script, audio_files, output_path):
        tmp = Path(tempfile.mkdtemp(prefix="steps_"))
        step_clips = []
        
        total_v_dur = self.get_duration(raw_video)

        try:
            for idx, step in enumerate(script):
                audio_path = audio_files[idx]["filename"]
                audio_dur = self.get_audio_duration(audio_path)

                # Parse timestamp MM:SS
                mm, ss = step["timestamp"].split(":")
                start = int(mm) * 60 + float(ss)
                
                # Safety: don't start after the video ends
                # Leave at least 0.1s for a valid cut
                if start >= total_v_dur:
                    start = max(0.0, total_v_dur - 0.1)

                base_clip = tmp / f"v_{idx:03d}.mp4"
                # If duration requested is longer than remaining video, ffmpeg handles it gracefully
                self.cut_segment(raw_video, start, audio_dur, base_clip)

                padded_clip = tmp / f"vpad_{idx:03d}.mp4"
                self.freeze_to_duration(base_clip, audio_dur, padded_clip)

                final_clip = tmp / f"final_{idx:03d}.mp4"
                self.attach_audio(padded_clip, audio_path, final_clip)

                step_clips.append(final_clip)

            self.concat_clips(step_clips, output_path)
        finally:
            # Cleanup temp working segments
            shutil.rmtree(tmp, ignore_errors=True)

    def get_video_size(self, path):
        out, _ = self.run_cmd([
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json",
            str(path)
        ])
        j = json.loads(out)
        s = j["streams"][0]
        return int(s["width"]), int(s["height"])

    def compute_layout(self, video_path, target_canvas=(1920, 1080), margin=160):
        vw, vh = self.get_video_size(video_path)
        cw, ch = target_canvas

        scale_w = cw - margin * 2
        scale_h = ch - margin * 2

        video_ar = vw / vh
        canvas_ar = cw / ch

        if video_ar >= canvas_ar:
            out_w = scale_w
            out_h = int(scale_w / video_ar)
        else:
            out_h = scale_h
            out_w = int(scale_h * video_ar)

        return cw, ch, out_w, out_h

    def add_background(self, video_path, bg_image, output_path):
        cw, ch, vw, vh = self.compute_layout(video_path)

        filter_complex = (
            f"[0:v]scale={cw}:{ch},setsar=1[bg];"
            f"[1:v]scale={vw}:{vh},setsar=1[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2"
        )

        self.run_cmd([
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(bg_image),
            "-i", str(video_path),
            "-filter_complex", filter_complex,
            "-map", "1:a?",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "20",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            "-movflags", "+faststart",
            str(output_path)
        ])
