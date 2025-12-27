import os
import shutil
import tempfile
from pathlib import Path
from src.application.video_service import VideoService
from src.infrastructure.storage_service import upload_file
from src.domain.repositories.video_repository import VideoRepository

class DocumentGenerationService:
    def __init__(self, video_repo: VideoRepository):
        self.video_repo = video_repo
        self.video_service = VideoService()

    def generate_guide(self, video_id: str):
        video = self.video_repo.get_by_id(video_id)
        if not video:
            raise ValueError(f"Video {video_id} not found")

        video_url = video.video_data.get("processed_video_url")
        if not video_url:
            raise ValueError("Video has not been processed yet (no video_url)")

        script = video.video_data.get("script", [])
        bucket_name = video.video_data.get("bucket", "default-bucket") # Need to resolve bucket name from somewhere if not in video_data
        
        # Fallback bucket extraction if URL is GCS public link
        if "storage.googleapis.com" in video_url:
            # https://storage.googleapis.com/BUCKET_NAME/path...
            try:
                parts = video_url.replace("https://storage.googleapis.com/", "").split("/", 1)
                bucket_name = parts[0]
            except:
                pass
        
        documentation_steps = []
        
        tmp_dir = Path(tempfile.mkdtemp(prefix="doc_gen_"))
        
        try:
            print(f"📄 Generating documentation for video {video_id}...")
            
            for i, seg in enumerate(script):
                # We skip deleted segments usually, but script SHOULD have is_deleted handled
                if seg.get("is_deleted") or seg.get("isDeleted"):
                    continue
                
                start_time = float(seg.get("start_time", 0))
                duration = float(seg.get("duration", 0))
                
                # Capture point: Start + 20% of duration, or +0.5s, clamped to duration
                # avoiding the very first frame of a transition if possible
                capture_offset = min(duration * 0.2, 0.5)
                capture_time = start_time + capture_offset
                
                screenshot_filename = f"step_{i:03d}_{seg['id']}.jpg"
                local_path = tmp_dir / screenshot_filename
                
                print(f"📸 Capturing frame at {capture_time:.2f}s for segment {seg['id']}")
                self.video_service.extract_frame(video_url, capture_time, local_path)
                
                # Upload
                blob_path = f"processed/{video_id}/docs/{screenshot_filename}"
                print(f"☁️ Uploading screenshot to {blob_path}")
                public_url = upload_file(bucket_name, str(local_path), blob_path)
                
                step_data = {
                    "segment_id": seg["id"],
                    "order": i + 1,
                    "timestamp": capture_time,
                    "screenshot_url": public_url,
                    "title": seg.get("ui_element", f"Step {i+1}"),
                    "action": seg.get("user_action", ""),
                    "voiceover_text": seg.get("voiceover_text", "")
                }
                documentation_steps.append(step_data)
                
            # Save to Video Data
            updated_doc = {
                "generated_at": str(os.times()), # Simple timestamp or use datetime
                "steps": documentation_steps
            }
            
            # Update DB
            self.video_repo.update(video_id, existing_video=video, video_data={"documentation": updated_doc})
            
            print(f"✅ Documentation generated with {len(documentation_steps)} steps.")
            return updated_doc

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
