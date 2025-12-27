import os
import shutil
import tempfile
import datetime
from pathlib import Path
from typing import Any
from src.application.video_service import VideoService
from src.infrastructure.storage_service import upload_file
from src.domain.repositories.video_repository import VideoRepository

from google.genai import types
import json

class DocumentGenerationService:
    def __init__(self, video_repo: VideoRepository, gemini_client: Any = None):
        self.video_repo = video_repo
        self.video_service = VideoService()
        self.client = gemini_client

    def generate_ai_markdown_guide(self, video_id: str, steps: list[dict]):
        """
        Uses Gemini to generate a polished Markdown document from the captured steps.
        """
        if not self.client:
            print("⚠️ No AI client available. Skipping AI refinement.")
            return ""

        video = self.video_repo.get_by_id(video_id)
        title = video.title or "Tutorial Guide"
        
        # Prepare context for AI
        steps_context = []
        for s in steps:
            steps_context.append({
                "order": s["order"],
                "title": s["title"],
                "action": s["action"],
                "voiceover_text": s["voiceover_text"],
                "screenshot_url": s["screenshot_url"]
            })

        prompt = f"""
        **TASK:** Create a professional, polished step-by-step user guide in Markdown format.
        **PRODUCT:** {title}

        **STYLE GUIDELINES:**
        1. **SPACING:** Use TWO full newlines (Double Enter) between every single element (Title, Intro, Steps, Headers, Paragraphs, Images). This is critical for readability.
        2. **TITLE:** Start with exactly one `# Heading 1`.
        3. **INTRODUCTION:** Immediately after the title, write a 2-sentence professional introduction in a blockquote (`> Discover how to...`).
        4. **STEPS:** For each step:
           - Use `## Step X: [Action Name]` as the header.
           - Use 2-3 sentences of clear instructional text.
           - Place the image on its own line: `![Screenshot](URL)`
        5. **STRUCTURE:** Each step MUST be separated from the previous one by multiple newlines.
        6. **TONE:** Professional and instructional.

        **DATA (JSON format):**
        {json.dumps(steps_context, indent=2)}

        **OUTPUT:** Return ONLY the Markdown content. Do not include ```markdown code block wrappers.
        """

        try:
            print(f"🪄 AI Refinement: Generating perfect guideline for {video_id}...")
            response = self.client.models.generate_content(
                model="gemini-2.0-flash-001",
                contents=[prompt],
                config=types.GenerateContentConfig(
                    temperature=0.2,
                )
            )
            
            markdown = response.text.strip()
            # Basic cleanup if AI adds ```markdown code blocks
            if markdown.startswith("```markdown"):
                markdown = markdown.replace("```markdown", "", 1).rstrip("```")
            elif markdown.startswith("```"):
                markdown = markdown.replace("```", "", 1).rstrip("```")
            
            return markdown.strip()

        except Exception as e:
            print(f"❌ AI Guide Generation Error: {e}")
            return ""

    def generate_guide(self, video_id: str):
        video = self.video_repo.get_by_id(video_id)
        if not video:
            raise ValueError(f"Video {video_id} not found")

        video_url = video.video_data.get("processed_video_url")
        if not video_url:
            raise ValueError("Video has not been processed yet (no video_url)")

        script = video.video_data.get("script", [])
        bucket_name = os.getenv("GCS_BUCKET_NAME", "evalsy-storage")
        
        documentation_steps = []
        
        tmp_dir = Path(tempfile.mkdtemp(prefix="doc_gen_"))
        
        # 1. Ensure we have a local video file if it's on GCS
        # FFmpeg often struggles with direct GCS URIs/Public URLs without auth
        local_video_path = video_url
        video_is_remote = video_url.startswith("gs://") or video_url.startswith("http")
        
        try:
            if video_is_remote:
                print(f"📥 Downloading video for frame extraction: {video_url}")
                # We reuse the logic from storage_service or just download to tmp
                if video_url.startswith("gs://"):
                    from src.infrastructure.storage_service import download_file
                    # Simple parse for gs://bucket/blob
                    parts = video_url[5:].split("/", 1)
                    v_bucket = parts[0]
                    v_blob = parts[1]
                    local_video_path = str(tmp_dir / "temp_video.mp4")
                    download_file(v_bucket, v_blob, local_video_path)
                else:
                    # It's an HTTP URL - if it's a GCS public URL, we might still need to download it
                    # for stability with FFmpeg
                    import requests
                    local_video_path = str(tmp_dir / "temp_video.mp4")
                    with requests.get(video_url, stream=True) as r:
                        r.raise_for_status()
                        with open(local_video_path, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                f.write(chunk)

            print(f"📄 Generating documentation for video {video_id}...")
            
            for i, seg in enumerate(script):
                if seg.get("is_deleted") or seg.get("isDeleted"):
                    continue
                
                start_time = float(seg.get("narration_start", seg.get("start_time", 0)))
                duration = float(seg.get("audio_duration", seg.get("duration", 0)))
                
                # Capture point: Start + offset
                capture_offset = min(duration * 0.2, 0.5)
                capture_time = start_time + capture_offset
                
                screenshot_filename = f"step_{i:03d}_{seg['id']}.jpg"
                local_path = tmp_dir / screenshot_filename
                
                print(f"📸 Capturing frame at {capture_time:.2f}s for segment {seg['id']}")
                try:
                    self.video_service.extract_frame(local_video_path, capture_time, local_path)
                    
                    if not local_path.exists():
                        print(f"⚠️ Warning: Frame extraction failed for segment {seg['id']} at {capture_time}s")
                        continue

                    # Upload
                    blob_path = f"processed/{video_id}/docs/{screenshot_filename}"
                    print(f"☁️ Uploading screenshot to {blob_path}")
                    public_url = upload_file(bucket_name, str(local_path), blob_path)
                    
                    if not public_url:
                        print(f"⚠️ Warning: Upload failed for {screenshot_filename}")
                        continue

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
                except Exception as e:
                    print(f"❌ Error processing segment {seg['id']}: {e}")
                    continue
                
            # 2. Generate AI-powered Markdown
            ai_markdown = self.generate_ai_markdown_guide(video_id, documentation_steps)
            
            # 3. Save to Video Data
            updated_doc = {
                "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "steps": documentation_steps,
                "markdown": ai_markdown
            }
            
            # Update DB
            self.video_repo.update(video_id, existing_video=video, documentation=updated_doc)
            
            print(f"✅ Documentation generated with {len(documentation_steps)} steps and AI content.")
            return updated_doc

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
