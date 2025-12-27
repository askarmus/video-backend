from typing import Any, Optional, Dict, List
import os
import shutil
import time
from src.config import VIDEO_BUCKET
from src.domain.repositories.video_repository import VideoRepository
from src.infrastructure.voice_service import generate_voiceover
from src.infrastructure.storage_service import download_file, upload_file
from src.infrastructure.workspace_manager import LocalWorkspace
from src.application.audio_service import AudioService
from src.application.video_service import VideoService

class SyncTimelineUseCase:
    def __init__(self, video_repo: VideoRepository):
        self.video_repo = video_repo
        self.audio_service = AudioService()
        self.video_service = VideoService()

    def execute_batch(self, video_id: str, user_id: str, updates: List[Dict[str, Any]], creds=None) -> Dict[str, Any]:
        """
        Simplified sync: regenerate updated voiceovers and update script metadata.
        We skip the complex master audio concatenation/rebuild.
        """
        # 1. Load and validate ownership
        video = self.video_repo.get_by_id(video_id)
        if not video:
            raise ValueError(f"Video {video_id} not found")
        if video.created_by != user_id:
            raise PermissionError("Unauthorized access to this video")

        script = video.video_data.get("script", [])
        project_id = video.video_data.get("project_id", "default")
        update_map = {u["id"]: u["voiceover_text"] for u in updates}
        
        # Determine bucket (reuse existing or default)
        bucket_name = video.video_data.get("bucket", VIDEO_BUCKET)

        with LocalWorkspace(prefix="audio_quick_") as ws:
            voiceovers_dir = ws.create_dir("voiceovers")
            
            # 2. Update segments and regenerate audio where needed
            for segment in script:
                seg_id = segment.get("id")
                if seg_id in update_map:
                    new_text = update_map[seg_id]
                    segment["voiceover_text"] = new_text
                    
                    print(f"🎤 Regenerating voiceover for segment {seg_id}...")
                    # Generate new voiceover MP3 using Google TTS
                    new_meta = generate_voiceover([segment], creds, output_dir=str(voiceovers_dir))[0]
                    local_path = new_meta["filename"]
                    
                    # Calculate new audio duration
                    new_dur = self.video_service.get_audio_duration(local_path)
                    segment["audio_duration"] = round(new_dur, 3)
                    segment["duration"] = round(new_dur, 3) 
                    
                    # Upload newly generated segment to GCS (returns public URL)
                    blob = f"processed/{project_id}/voiceovers/{os.path.basename(local_path)}"
                    seg_url = upload_file(bucket_name, local_path, blob)
                    segment["audio_url"] = seg_url

            # 3. Recalculate timeline timestamps (to keep them contiguous)
            current_time = 0.0
            gap = 0.5
            for i, seg in enumerate(script):
                seg["start_time"] = round(current_time, 3)
                
                # Format timestamp as HH:MM:SS for the UI/TTS naming
                m, s = divmod(int(current_time), 60)
                h, m = divmod(m, 60)
                seg["timestamp"] = f"{h:02d}:{m:02d}:{s:02d}"
                
                dur = seg.get("audio_duration", 1.0)
                seg["end_time"] = round(current_time + dur, 3)
                
                if i < len(script) - 1:
                    pause = seg.get("pause_duration", gap)
                    current_time = seg["end_time"] + pause
                else:
                    current_time = seg["end_time"]
            
            total_duration = round(current_time, 3)
            
            # 4. Persist updated script and metadata to database
            updated_data = {
                "script": script,
                "duration": total_duration
            }
            # Perform a deep merge update for video_data
            self.video_repo.update(video_id, video_data=updated_data, download_ready=False)
            
            return {
                "status": "success",
                "total_duration": total_duration,
                "script": script
            }
