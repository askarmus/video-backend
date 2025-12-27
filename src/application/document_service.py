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
        
        # 1. Load existing images to reuse
        existing_doc = video.documentation or {}
        image_library = existing_doc.get("images", {})
        
        tmp_dir = Path(tempfile.mkdtemp(prefix="doc_gen_"))
        local_video_path = None
        
        def ensure_video_downloaded():
            nonlocal local_video_path
            if local_video_path:
                return local_video_path
            
            video_is_remote = video_url.startswith("gs://") or video_url.startswith("http")
            if not video_is_remote:
                local_video_path = video_url
                return local_video_path

            print(f"📥 Downloading video for frame extraction: {video_url}")
            local_video_path = str(tmp_dir / "temp_video.mp4")
            
            if video_url.startswith("gs://"):
                from src.infrastructure.storage_service import download_file
                parts = video_url[5:].split("/", 1)
                download_file(parts[0], parts[1], local_video_path)
            else:
                import requests
                with requests.get(video_url, stream=True) as r:
                    r.raise_for_status()
                    with open(local_video_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
            return local_video_path

        try:
            print(f"📄 Generating documentation for video {video_id}...")
            
            for i, seg in enumerate(script):
                if seg.get("is_deleted") or seg.get("isDeleted"):
                    continue
                
                seg_id = seg['id']
                start_time = float(seg.get("narration_start", seg.get("start_time", 0)))
                duration = float(seg.get("audio_duration", seg.get("duration", 0)))
                capture_offset = min(duration * 0.2, 0.5)
                capture_time = start_time + capture_offset

                # Reuse logic
                if seg_id in image_library:
                    print(f"♻️ Reusing existing screenshot for segment {seg_id}")
                    public_url = image_library[seg_id]
                else:
                    # Actually capture it
                    screenshot_filename = f"step_{i:03d}_{seg_id}.jpg"
                    local_path = tmp_dir / screenshot_filename
                    
                    try:
                        v_path = ensure_video_downloaded()
                        print(f"📸 Capturing frame at {capture_time:.2f}s for segment {seg_id}")
                        self.video_service.extract_frame(v_path, capture_time, local_path)
                        
                        if not local_path.exists():
                            print(f"⚠️ Warning: Frame extraction failed for segment {seg_id}")
                            continue

                        # Upload
                        blob_path = f"processed/{video_id}/docs/{screenshot_filename}"
                        print(f"☁️ Uploading screenshot to {blob_path}")
                        public_url = upload_file(bucket_name, str(local_path), blob_path)
                        
                        if not public_url:
                            continue

                        # Add to library
                        image_library[seg_id] = public_url
                        
                    except Exception as e:
                        print(f"❌ Error capturing segment {seg_id}: {e}")
                        continue

                step_data = {
                    "segment_id": seg_id,
                    "order": i + 1,
                    "timestamp": capture_time,
                    "screenshot_url": public_url,
                    "title": seg.get("ui_element", f"Step {i+1}"),
                    "action": seg.get("user_action", ""),
                    "voiceover_text": seg.get("voiceover_text", "")
                }
                documentation_steps.append(step_data)
                
            # 3. Generate AI-powered Markdown
            ai_markdown = self.generate_ai_markdown_guide(video_id, documentation_steps)
            
            # 4. Save to Video Data
            updated_doc = {
                "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "steps": documentation_steps,
                "markdown": ai_markdown,
                "images": image_library # Preserve the library
            }
            
            # Update DB
            self.video_repo.update(video_id, existing_video=video, documentation=updated_doc)
            
            print(f"✅ Documentation generated with {len(documentation_steps)} steps. {len(image_library)} images in library.")
            return updated_doc

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
