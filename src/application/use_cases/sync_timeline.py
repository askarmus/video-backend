from typing import Any
import os
import tempfile
import shutil
import time
from src.domain.repositories.video_repository import VideoRepository
from src.infrastructure.voice_service import generate_voiceover
from src.infrastructure.storage_service import download_file, upload_file, parse_gcs_uri
from src.application.audio_service import AudioService
from src.application.video_service import VideoService

class SyncTimelineUseCase:
    def __init__(self, video_repo: VideoRepository):
        self.video_repo = video_repo
        self.audio_service = AudioService()
        self.video_service = VideoService()

    def execute_batch(self, video_id: str, user_id: str, updates: list[dict[str, str]], creds=None):
        """
        Surgical Master-Slicing Logic:
        1. Downloads the existing Master Audio once.
        2. Generates only the new voice segments.
        3. Uses FFmpeg to 'slice' unchanged parts from the Master.
        4. Re-concatenates into a new version.
        """
        video = self.video_repo.get_by_id(video_id)
        if not video:
            raise ValueError(f"Video {video_id} not found")

        if video.created_by != user_id:
            raise PermissionError("Unauthorized")

        script = video.video_data.get("script", [])
        project_id = video.video_data.get("project_id", "default")
        
        # Determine Source Master
        master_url = video.video_data.get("processed_audio_url")
        bucket_name, master_blob = parse_gcs_uri(master_url) if master_url else (None, None)
        if not bucket_name:
            bucket_name = os.getenv("VIDEO_BUCKET", "evalsy-storage")

        tmp_dir = tempfile.mkdtemp(prefix="audio_surgical_")
        voiceovers_dir = os.path.join(tmp_dir, "voiceovers")
        os.makedirs(voiceovers_dir, exist_ok=True)
        
        try:
            # 1. PREP MASTER (Download once)
            local_old_master = None
            master_duration = 0
            if bucket_name and master_blob:
                print(f"📥 Downloading base master for surgical slicing...")
                local_old_master_path = os.path.join(tmp_dir, "old_master.mp3")
                if download_file(bucket_name, master_blob, local_old_master_path):
                    local_old_master = local_old_master_path
                    master_duration = self.video_service.get_audio_duration(local_old_master)
                    print(f"📏 Master check: {master_duration}s total.")
                else:
                    print(f"⚠️ Master download failed. Falling back to individual segment downloads.")
                    local_old_master = None

            update_map = {u["id"]: u["voiceover_text"] for u in updates}
            processed_audio_list = []
            
            # 2. GATHER SECTIONS (Regen OR Slice OR Full-Download Fallback)
            for segment in script:
                seg_id = segment.get("id")
                voice_text = update_map.get(seg_id)
                local_seg_path = os.path.join(voiceovers_dir, f"{seg_id}.mp3")

                if voice_text is not None or not (segment.get("audio_url") or segment.get("url") or local_old_master):
                    # REGENERATE (If updated OR if audio is completely missing from all sources)
                    gen_reason = "Updated" if voice_text is not None else "Missing Source"
                    print(f"🎤 [{gen_reason}] {seg_id}...")
                    
                    if voice_text is not None:
                        segment["voiceover_text"] = voice_text
                    
                    new_meta = generate_voiceover([segment], creds, output_dir=voiceovers_dir)[0]
                    local_seg_path = new_meta["filename"]
                
                else:
                    # Not being updated. Try Slice, then GS Fallback, then HTTP Fallback
                    start = segment.get("start_time", 0.0)
                    dur = segment.get("audio_duration", 1.0)
                    if dur <= 0: dur = 0.5
                    end = start + dur

                    if local_old_master and end <= (master_duration + 0.1):
                        print(f"✂️ [Exact Slice] {seg_id} | Range: {start}s - {end}s")
                        self.audio_service.run_cmd([
                            "ffmpeg", "-y", "-i", local_old_master,
                            "-filter_complex", f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[out]",
                            "-map", "[out]",
                            "-acodec", "libmp3lame", "-ar", "44100", "-b:a", "128k", 
                            local_seg_path
                        ])
                    else:
                        gcs_url = segment.get("audio_url") or segment.get("url")
                        print(f"🪂 [Source Search] {seg_id} from {gcs_url}")
                        
                        if gcs_url.startswith("gs://"):
                            sb, sblob = parse_gcs_uri(gcs_url)
                            download_file(sb, sblob, local_seg_path)
                        elif gcs_url.startswith("http"):
                            import requests
                            print(f"🌐 [HTTP Download] {seg_id}")
                            r = requests.get(gcs_url, stream=True)
                            with open(local_seg_path, 'wb') as f:
                                for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
                        else:
                            # Final fallback: if URL is weird, just regen to be safe
                            print(f"🎤 [Deep Fallback Regen] {seg_id}")
                            new_meta = generate_voiceover([segment], creds, output_dir=voiceovers_dir)[0]
                            local_seg_path = new_meta["filename"]
                
                duration = self.video_service.get_audio_duration(local_seg_path)
                processed_audio_list.append({
                    "id": seg_id,
                    "local_path": local_seg_path,
                    "duration": duration,
                    "segment": segment
                })

            # 3. REBUILD TIMELINE (Sequential Ripple Sync)
            current_time = 0.0
            concat_list = []
            gap = 0.5 # Default breath/pause gap

            for i, item in enumerate(processed_audio_list):
                seg = item["segment"]
                new_dur = round(item["duration"], 3)
                
                # Capture original values for delta calculation
                orig_start = seg.get("start_time", 0.0)
                orig_dur = seg.get("audio_duration", 0.0)
                
                # Apply New Sequential Timing
                seg["start_time"] = round(current_time, 3)
                seg["audio_duration"] = new_dur
                seg["duration"] = new_dur
                seg["end_time"] = round(current_time + new_dur, 3)
                
                # Calculate Deltas (User Request: + if longer, - if shorter)
                seg["audio_delta"] = round(new_dur - orig_dur, 3)
                seg["timeline_shift"] = round(seg["start_time"] - orig_start, 3)
                
                concat_list.append({"filename": item["local_path"]})
                
                # Handle Pauses
                if i < len(processed_audio_list) - 1:
                    pause = seg.get("pause_duration", gap)
                    seg["pause_duration"] = pause # Ensure it's persisted
                    
                    silence_path = os.path.join(tmp_dir, f"gap_{i}.mp3")
                    self.audio_service.generate_silence(pause, silence_path)
                    concat_list.append({"filename": silence_path})
                    
                    current_time = seg["end_time"] + pause
                else:
                    current_time = seg["end_time"]

            # 4. EXPORT & SYNC
            master_name = f"voice_v{int(time.time())}.mp3"
            local_final = os.path.join(tmp_dir, master_name)
            self.audio_service.concat_audio_files(concat_list, local_final, tmp_dir)
            
            # Upload new master
            final_url = upload_file(bucket_name, local_final, f"processed/{project_id}/{master_name}")
            
            # Upload updated segments only
            for item in processed_audio_list:
                if item["id"] in update_map:
                    blob = f"processed/{project_id}/voiceovers/{os.path.basename(item['local_path'])}"
                    seg_url = upload_file(bucket_name, item["local_path"], blob)
                    for s in script:
                        if s["id"] == item["id"]: s["audio_url"] = seg_url

            # MANDATORY RULE: Global duration MUST match final script end_time
            if script:
                total_duration = round(script[-1]["end_time"], 3)
            else:
                total_duration = 0.0

            # Atomic Database Update (Updating both script and the global duration invariant)
            updated_data = {
                "script": script,
                "processed_audio_url": final_url,
                "duration": total_duration
            }
            
            # Validation Assertion (Hard Error if broken)
            if script and abs(updated_data["duration"] - script[-1]["end_time"]) > 0.01:
                raise RuntimeError(f"Timeline Invariant Broken: Duration ({updated_data['duration']}) != Final End Time ({script[-1]['end_time']})")

            self.video_repo.update(video_id, video_data=updated_data)
            
            return {
                "merged_audio_url": final_url,
                "total_duration": total_duration,
                "script": script
            }

        except Exception as e:
            print(f"❌ Surgical Build Error: {e}")
            raise
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
