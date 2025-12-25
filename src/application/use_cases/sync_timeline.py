from typing import Any, Optional, Dict, List
import os
import shutil
import time
from src.config import VIDEO_BUCKET
from src.domain.repositories.video_repository import VideoRepository
from src.infrastructure.voice_service import generate_voiceover
from src.infrastructure.storage_service import download_file, upload_file, parse_gcs_uri
from src.infrastructure.workspace_manager import LocalWorkspace
from src.application.audio_service import AudioService
from src.application.video_service import VideoService

class SyncTimelineUseCase:
    def __init__(self, video_repo: VideoRepository):
        self.video_repo = video_repo
        self.audio_service = AudioService()
        self.video_service = VideoService()

    def execute_batch(self, video_id: str, user_id: str, updates: List[Dict[str, Any]], creds=None) -> Dict[str, Any]:
        """High-level orchestration for surgical audio regeneration and timeline sync."""
        video = self._load_and_validate_video(video_id, user_id)
        script = video.video_data.get("script", [])
        project_id = video.video_data.get("project_id", "default")
        update_map = {u["id"]: u["voiceover_text"] for u in updates}

        master_url = video.video_data.get("processed_audio_url")
        bucket_name, master_blob = parse_gcs_uri(master_url) if master_url else (None, None)
        bucket_name = bucket_name or VIDEO_BUCKET

        with LocalWorkspace(prefix="audio_surgical_") as ws:
            voiceovers_dir = ws.create_dir("voiceovers")
            
            try:
                local_old_master, master_duration = self._prepare_master_audio(bucket_name, master_blob, ws)
                
                processed_audio_list = self._process_segments(
                    script, update_map, local_old_master, master_duration, voiceovers_dir, ws, creds
                )

                final_audio_url, total_duration = self._rebuild_and_export_timeline(
                    processed_audio_list, ws, bucket_name, project_id
                )

                self._persist_updates(
                    video_id, project_id, bucket_name, processed_audio_list, 
                    update_map, script, final_audio_url, total_duration
                )

                return {
                    "merged_audio_url": final_audio_url,
                    "total_duration": total_duration,
                    "script": script
                }

            except Exception as e:
                print(f"❌ Surgical Build Error: {e}")
                raise

    def _load_and_validate_video(self, video_id: str, user_id: str) -> Any:
        video = self.video_repo.get_by_id(video_id)
        if not video:
            raise ValueError(f"Video {video_id} not found")
        if video.created_by != user_id:
            raise PermissionError("Unauthorized")
        return video

    def _prepare_master_audio(self, bucket_name: str, master_blob: Optional[str], ws: LocalWorkspace) -> tuple:
        if not (bucket_name and master_blob):
            return None, 0

        print(f"📥 Downloading base master for surgical slicing...")
        local_old_master_path = ws.get_path("old_master.mp3")
        if download_file(bucket_name, master_blob, local_old_master_path):
            duration = self.video_service.get_audio_duration(local_old_master_path)
            print(f"📏 Master check: {duration}s total.")
            return local_old_master_path, duration
        
        print(f"⚠️ Master download failed. Falling back to individual segment downloads.")
        return None, 0

    def _process_segments(self, script: List[Dict], update_map: Dict, local_old_master: Optional[str], 
                          master_duration: float, voiceovers_dir: Any, ws: LocalWorkspace, creds: Any) -> List[Dict]:
        processed_audio_list = []
        for segment in script:
            seg_id = segment.get("id")
            voice_text = update_map.get(seg_id)
            local_seg_path = ws.get_path("voiceovers", f"{seg_id}.mp3")

            if self._should_regenerate_segment(segment, voice_text, local_old_master):
                local_seg_path = self._regenerate_segment(segment, voiceovers_dir, creds, voice_text)
            else:
                local_seg_path = self._resolve_existing_segment(
                    segment, local_old_master, master_duration, local_seg_path, voiceovers_dir, creds
                )

            duration = self.video_service.get_audio_duration(local_seg_path)
            processed_audio_list.append({
                "id": seg_id,
                "local_path": local_seg_path,
                "duration": duration,
                "segment": segment
            })
        return processed_audio_list

    def _should_regenerate_segment(self, segment: Dict, voice_text: Optional[str], local_old_master: Optional[str]) -> bool:
        if voice_text is not None:
            return True
        # Regen if audio missing from all sources
        has_source = segment.get("audio_url") or segment.get("url") or local_old_master
        return not has_source

    def _regenerate_segment(self, segment: Dict, voiceovers_dir: Any, creds: Any, voice_text: Optional[str] = None) -> str:
        gen_reason = "Updated" if voice_text is not None else "Missing Source"
        print(f"🎤 [{gen_reason}] {segment.get('id')}...")
        if voice_text is not None:
            segment["voiceover_text"] = voice_text
        new_meta = generate_voiceover([segment], creds, output_dir=str(voiceovers_dir))[0]
        return new_meta["filename"]

    def _resolve_existing_segment(self, segment: Dict, local_old_master: Optional[str], 
                                  master_duration: float, local_seg_path: str, voiceovers_dir: Any, creds: Any) -> str:
        start = segment.get("start_time", 0.0)
        dur = segment.get("audio_duration", 1.0)
        if dur <= 0: dur = 0.5
        end = start + dur

        if local_old_master and end <= (master_duration + 0.1):
            return self._slice_from_master(local_old_master, start, end, local_seg_path, segment.get("id"))
        
        gcs_url = segment.get("audio_url") or segment.get("url")
        print(f"🪂 [Source Search] {segment.get('id')} from {gcs_url}")
        
        if gcs_url and gcs_url.startswith("gs://"):
            return self._download_segment(gcs_url, local_seg_path)
        elif gcs_url and gcs_url.startswith("http"):
            return self._download_http_segment(gcs_url, local_seg_path, segment.get("id"))
        
        print(f"🎤 [Deep Fallback Regen] {segment.get('id')}")
        return self._regenerate_segment(segment, voiceovers_dir, creds)

    def _slice_from_master(self, master_path: str, start: float, end: float, output_path: str, seg_id: str) -> str:
        print(f"✂️ [Exact Slice] {seg_id} | Range: {start}s - {end}s")
        self.audio_service.run_cmd([
            "ffmpeg", "-y", "-i", master_path,
            "-filter_complex", f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[out]",
            "-map", "[out]",
            "-acodec", "libmp3lame", "-ar", "44100", "-b:a", "128k", 
            output_path
        ])
        return output_path

    def _download_segment(self, gcs_url: str, local_path: str) -> str:
        sb, sblob = parse_gcs_uri(gcs_url)
        download_file(sb, sblob, local_path)
        return local_path

    def _download_http_segment(self, url: str, local_path: str, seg_id: str) -> str:
        import requests
        print(f"🌐 [HTTP Download] {seg_id}")
        r = requests.get(url, stream=True)
        with open(local_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
        return local_path

    def _rebuild_and_export_timeline(self, processed_audio_list: List[Dict], ws: LocalWorkspace, 
                                     bucket_name: str, project_id: str) -> tuple:
        current_time = 0.0
        concat_list = []
        gap = 0.5

        for i, item in enumerate(processed_audio_list):
            seg = item["segment"]
            new_dur = round(item["duration"], 3)
            orig_start = seg.get("start_time", 0.0)
            orig_dur = seg.get("audio_duration", 0.0)
            
            seg["start_time"] = round(current_time, 3)
            seg["audio_duration"] = new_dur
            seg["duration"] = new_dur
            seg["end_time"] = round(current_time + new_dur, 3)
            seg["audio_delta"] = round(new_dur - orig_dur, 3)
            seg["timeline_shift"] = round(seg["start_time"] - orig_start, 3)
            
            concat_list.append({"filename": item["local_path"]})
            
            if i < len(processed_audio_list) - 1:
                pause = seg.get("pause_duration", gap)
                seg["pause_duration"] = pause
                silence_path = ws.get_path(f"gap_{i}.mp3")
                self.audio_service.generate_silence(pause, silence_path)
                concat_list.append({"filename": silence_path})
                current_time = seg["end_time"] + pause
            else:
                current_time = seg["end_time"]

        master_name = f"voice_v{int(time.time())}.mp3"
        local_final = ws.get_path(master_name)
        self.audio_service.concat_audio_files(concat_list, local_final, str(ws.path))
        
        final_url = upload_file(bucket_name, local_final, f"processed/{project_id}/{master_name}")
        return final_url, round(current_time, 3)

    def _persist_updates(self, video_id: str, project_id: str, bucket_name: str, 
                         processed_audio_list: List[Dict], update_map: Dict, script: List[Dict], 
                         final_url: str, total_duration: float):
        for item in processed_audio_list:
            if item["id"] in update_map:
                blob = f"processed/{project_id}/voiceovers/{os.path.basename(item['local_path'])}"
                seg_url = upload_file(bucket_name, item["local_path"], blob)
                for s in script:
                    if s["id"] == item["id"]: s["audio_url"] = seg_url

        if script and abs(total_duration - script[-1]["end_time"]) > 0.01:
            raise RuntimeError(f"Timeline Invariant Broken: Duration ({total_duration}) != Final End Time ({script[-1]['end_time']})")

        updated_data = {
            "script": script,
            "processed_audio_url": final_url,
            "duration": total_duration
        }
        self.video_repo.update(video_id, video_data=updated_data)
