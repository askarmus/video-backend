from typing import Any
from src.domain.repositories.video_repository import VideoRepository

class SyncTimelineUseCase:
    def __init__(self, video_repo: VideoRepository):
        self.video_repo = video_repo

    def _timestamp_to_seconds(self, ts):
        if not ts: return 0.0
        parts = ts.split(':')
        if len(parts) == 1:
            return float(parts[0])
        return int(parts[0]) * 60 + float(parts[1])

    def _seconds_to_timestamp(self, seconds):
        m = int(seconds // 60)
        s = seconds % 60
        return f"{m:02d}:{s:05.2f}"

    def execute_batch(self, video_id: str, user_id: str, updates: list[dict[str, str]], creds=None):
        """
        Handles multiple script updates, regenerates audio, and re-calculates the timeline.
        """
        import os
        import tempfile
        import shutil
        from src.infrastructure.voice_service import generate_voiceover
        from src.infrastructure.storage_service import download_file, upload_file, parse_gcs_uri
        from src.application.audio_service import AudioService
        from src.application.video_service import VideoService

        video = self.video_repo.get_by_id(video_id)
        if not video:
            raise ValueError(f"Video {video_id} not found")

        if video.created_by != user_id:
            raise PermissionError("Unauthorized")

        script = video.video_data.get("script", [])
        project_id = video.video_data.get("project_id", "default")
        
        # Determine bucket from existing processed URLs (preferring audio-related ones first)
        sample_url = (
            video.video_data.get("processed_audio_url") or 
            video.video_data.get("processed_video_url") or 
            (script[0].get("audio_url") if script else "")
        )
        bucket_name, _ = parse_gcs_uri(sample_url)
        if not bucket_name:
            # Fallback to env or assume from video_id
            bucket_name = os.getenv("VIDEO_BUCKET", "evalsy-storage")

        # Prep working dir
        tmp_dir = tempfile.mkdtemp(prefix="batch_audio_")
        voiceovers_dir = os.path.join(tmp_dir, "voiceovers")
        os.makedirs(voiceovers_dir, exist_ok=True)
        
        audio_service = AudioService()
        video_service = VideoService()
        
        try:
            update_map = {u["id"]: u["voiceover_text"] for u in updates}
            audio_files = []
            
            # 1. Update text and gather/generate audio
            for i, segment in enumerate(script):
                seg_id = segment.get("id")
                is_updated = seg_id in update_map
                
                if is_updated:
                    segment["voiceover_text"] = update_map[seg_id]
                    print(f"🎤 Regenerating audio for segment {seg_id}...")
                    # Generate single segment audio
                    new_audio = generate_voiceover([segment], creds, output_dir=voiceovers_dir)
                    audio_files.append(new_audio[0])
                else:
                    # Download existing audio from GCS
                    gcs_url = segment.get("audio_url")
                    if gcs_url and gcs_url.startswith("gs://"):
                        b, blob = parse_gcs_uri(gcs_url)
                        local_path = os.path.join(voiceovers_dir, os.path.basename(blob))
                        download_file(b, blob, local_path)
                        
                        audio_files.append({
                            "id": seg_id,
                            "filename": local_path,
                            "timestamp": segment["timestamp"],
                            "text": segment["voiceover_text"]
                        })
                    else:
                        print(f"⚠️ Warning: No audio_url for segment {seg_id}")

            # 2. Resolve Timeline (Ripple Effect)
            print("⌛ Recalculating timeline to remove gaps and prevent collisions...")
            next_available = 0.0
            gap = 0.3 # 300ms gap
            
            for i, seg_meta in enumerate(audio_files):
                # Always place segment at the next available slot to maintain sequential flow
                new_start = next_available
                duration = video_service.get_audio_duration(seg_meta['filename'])
                
                new_ts = self._seconds_to_timestamp(new_start)
                seg_meta['timestamp'] = new_ts
                script[i]['timestamp'] = new_ts
                
                # Update next available slot
                next_available = new_start + duration + gap


            # 3. Concatenate Master Audio
            final_audio_path = os.path.join(tmp_dir, f"narration_updated.mp3")
            audio_service.concat_audio_files(audio_files, final_audio_path, tmp_dir)
            
            # 4. Upload Assets
            # Upload new master
            master_blob = f"processed/{project_id}/narration_updated_{int(os.path.getmtime(final_audio_path))}.mp3"
            new_master_url = upload_file(bucket_name, final_audio_path, master_blob)
            
            # Upload ONLY the newly generated voiceovers
            for i, seg_id in enumerate(update_map.keys()):
                # Find the segment in audio_files
                new_seg = next((a for a in audio_files if a['id'] == seg_id), None)
                if new_seg:
                    blob_name = f"processed/{project_id}/voiceovers/{os.path.basename(new_seg['filename'])}"
                    new_seg_url = upload_file(bucket_name, new_seg['filename'], blob_name)
                    # Update script with new GCS URL
                    for s in script:
                        if s['id'] == seg_id:
                            s['audio_url'] = new_seg_url
            
            # 5. Save back to DB
            updated_video_data = {
                "script": script,
                "processed_audio_url": new_master_url
            }
            self.video_repo.update(video_id, video_data=updated_video_data)
            
            return {
                "status": "success",
                "processed_audio_url": new_master_url,
                "script": script
            }

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

   