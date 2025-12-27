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
        1. **TITLE:** Use a single # Heading 1 for the main title.
        2. **INTRODUCTION:** Immediately after the title, write a 2-sentence professional introduction explaining what this guide covers and its value. Wrap this introduction in a Markdown blockquote (e.g., '> Discover how to...').
        3. **STEPS:** For each step:
           - Use ## Step X: [Action Name] as the header.
           - Write a clear, instructional paragraph (2-3 sentences) describing the action. Do not just copy the voiceover; make it read like a manual.
           - Place the image immediately after the text using: ![Screenshot](URL)
        4. **TONE:** Professional, instructional, and concise.

        **DATA (JSON format):**
        {json.dumps(steps_context, indent=2)}

        **OUTPUT:** Return ONLY the Markdown content.
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
        bucket_name = video.video_data.get("bucket", "default-bucket") # Need to resolve bucket name from somewhere if not in video_data
        
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
