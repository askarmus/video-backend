import os
import uuid
import time
from datetime import datetime
from src.application.script_service import create_ai_voice_script, load_script, save_script
from src.infrastructure.voice_service import generate_voiceover
from src.infrastructure.storage_service import download_file, upload_file, parse_gcs_uri
from src.application.video_service import VideoService
from src.application.audio_service import AudioService
from src.application.use_cases.create_video import CreateVideoUseCase

class NarrationPipeline:
    def __init__(self, gemini_client, tts_creds, base_dir):
        self.client = gemini_client
        self.creds = tts_creds
        self.base_dir = base_dir
        
        # Centralized output directory
        self.output_dir = os.path.join(base_dir, "output")
        os.makedirs(self.output_dir, exist_ok=True)
        
        self.video_service = VideoService()
        self.audio_service = AudioService()


    def _timestamp_to_seconds(self, ts):
        parts = ts.split(':')
        if len(parts) == 1:
            return float(parts[0])
        return int(parts[0]) * 60 + float(parts[1])

    def _seconds_to_timestamp(self, seconds):
        m = int(seconds // 60)
        s = seconds % 60
        return f"{m:02d}:{s:05.2f}"

    def resolve_timeline(self, audio_files, script):
        """Adjusts timestamps in both audio_files and script to prevent overlapping."""
        print(f"⌛ [Timeline] Resolving collisions...")
        next_available = 0.0
        gap = 0.3 # 300ms gap
        collisions = 0

        for i, seg in enumerate(audio_files):
            current_start = self._timestamp_to_seconds(seg['timestamp'])
            duration = self.video_service.get_audio_duration(seg['filename'])
            
            if current_start < next_available:
                current_start = next_available
                new_ts = self._seconds_to_timestamp(current_start)
                seg['timestamp'] = new_ts
                script[i]['timestamp'] = new_ts
                collisions += 1
            
            next_available = current_start + duration + gap

        if collisions > 0:
            print(f"  ⚠️ Fixed {collisions} overlapping segments.")
        else:
            print(f"  ✅ No audio collisions detected.")
            
        return audio_files, script

    def download_video(self, gcs_uri):
        """Helper to download a video from GCS"""
        bucket_name, blob_name = parse_gcs_uri(gcs_uri)
        if not bucket_name:
            raise ValueError(f"Invalid GCS URI: {gcs_uri}")
        
        base_name = os.path.splitext(blob_name)[0]
        local_path = os.path.join(self.output_dir, f"raw_{base_name}.mp4")
        
        if os.path.exists(local_path):
            print(f"  📂 Using existing local raw video: {local_path}")
            return local_path
            
        local_raw = download_file(bucket_name, blob_name, local_path)
        if not local_raw:
            raise RuntimeError(f"Failed to download video from {gcs_uri}")
        return local_raw

    def upload_asset(self, local_path, destination_blob):
        """Helper to upload a local file to GCS"""
        bucket_name = os.getenv("VIDEO_URI").replace("gs://", "").split("/")[0]
        return upload_file(bucket_name, local_path, destination_blob)

    def run(self, local_raw_path, gcs_video_uri):
        pipeline_start = time.time()
        timings = {}

        print(f"\n🚀 CORE NARRATION PIPELINE")
        print(f"-" * 40)
        
        # Setup unique project identity
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:4]
        base_name = os.path.splitext(os.path.basename(local_raw_path))[0].replace("raw_", "")
        project_id = f"{base_name}_{timestamp}_{unique_id}"
        
        # Determine GCS bucket
        bucket_name = os.getenv("VIDEO_URI").replace("gs://", "").split("/")[0] if os.getenv("VIDEO_URI") else None
        
        # Create project-specific local directory

        project_dir = os.path.join(self.output_dir, project_id)
        voiceovers_dir = os.path.join(project_dir, "voiceovers")
        os.makedirs(voiceovers_dir, exist_ok=True)
        
        script_file = os.path.join(project_dir, "ai_voiceover_script.json")
        
        # 1. Trim
        trim_start = time.time()
        unique_trimmed_name = f"trimmed_{base_name}.mp4"
        local_trimmed = os.path.join(project_dir, unique_trimmed_name)
        
        print(f"✂️ [1/5] Trimming Video...")
        self.video_service.fast_trim(local_raw_path, local_trimmed)
        timings["Video Trim"] = time.time() - trim_start
        
        # Upload trimmed video to GCS so Gemini can analyze it
        upload_start = time.time()
        use_local = os.getenv("ENV", "local").lower() == "local"
        if not use_local:
            print(f"☁️  Uploading trimmed video for analysis...")
            gcs_trimmed_uri = self.upload_asset(local_trimmed, f"processed/{project_id}/{unique_trimmed_name}")
            timings["Video upload"] = time.time() - upload_start
        else:
            print(f"⏩ Skipping trimmed upload (Local Mode)")
            gcs_trimmed_uri = gcs_video_uri # Fallback to original

        # 2. Scripting
        step_start = time.time()
        print(f"📝 [2/5] Generating AI Script...")
        
        script = load_script(script_file)
        if not script:
            # Use the trimmed video URI for better script accuracy
            script = create_ai_voice_script(self.client, gcs_trimmed_uri)
            if script:
                save_script(script, script_file)
        
        if not script:
            print("❌ Error: Could not generate script.")
            return None
        timings["AI Scripting"] = time.time() - step_start

        # 3. Voice Generation
        step_start = time.time()
        print(f"🎤 [3/5] Synthesizing Narrations ({len(script)} lines)...")
        # Ensure we pass the project-specific voiceovers directory
        audio_files = generate_voiceover(script, self.creds, output_dir=voiceovers_dir)
        timings["Voice synthesis"] = time.time() - step_start

        # 4. Final Assembler
        print(f"🎬 [4/5] Assembling Final Video...")
        
        # Resolve timeline overlaps before assembly
        resolve_start = time.time()
        audio_files, script = self.resolve_timeline(audio_files, script)
        timings["Collision Fix"] = time.time() - resolve_start
        
        assemble_start = time.time()
        final_video_name = f"final_{base_name}.mp4"
        final_video_path = os.path.join(project_dir, final_video_name)
        self.video_service.assemble_steps(raw_video=local_trimmed, script=script, audio_files=audio_files, output_path=final_video_path)
        timings["Video Assembly"] = time.time() - assemble_start
        
        # Create MP3
        audio_concat_start = time.time()
        final_audio_name = f"narration_{base_name}.mp3"
        final_audio_path = os.path.join(project_dir, final_audio_name)
        self.audio_service.concat_audio_files(audio_files, final_audio_path, project_dir)
        timings["Audio Concat"] = time.time() - audio_concat_start

        # 5. Cloud Upload (All assets in project folder)
        if not use_local:
            print(f"☁️  [5/5] Syncing all assets to Cloud Storage...")
            # Upload individual voiceovers
            for audio in audio_files:
                audio_blob = f"processed/{project_id}/voiceovers/{os.path.basename(audio['filename'])}"
                self.upload_asset(audio['filename'], audio_blob)
            
            # Upload final products
            self.upload_asset(final_video_path, f"processed/{project_id}/{final_video_name}")
            self.upload_asset(final_audio_path, f"processed/{project_id}/{final_audio_name}")
            self.upload_asset(script_file, f"processed/{project_id}/ai_voiceover_script.json")
            print(f"  ✅ All assets uploaded to GCS folder: processed/{project_id}/")


        metadata = {
                    "file_type": request.file_type,
                    "duration": request.duration,
                    "user_ip": request.user_ip,
                    "user_country": request.user_country,
                    "processed_video_url": final_video_url,
                    "script": results["script"],
                    "project_id": results.get("project_id")
                }
        
        use_case.execute(user_id=user.id, video_id=request.video_id,title=request.title,video_uri=request.video_uri, metadata=metadata)

        # Summary
        total_pipeline_time = time.time() - pipeline_start
        
        print(f"\n✨ PROCESSING COMPLETE")
        print(f"-" * 40)
        print(f"📊 TIMELINE SUMMARY:")
        for step, duration in timings.items():
            print(f"  • {step.ljust(18)}: {duration:6.1f}s")
        print(f"  {'-' * 28}")
        print(f"  • {'TOTAL'.ljust(18)}: {total_pipeline_time:6.1f}s")
        print(f"-" * 40)
        
        return {
            "project_id": project_id,
            "project_dir": project_dir,
            "video_path": final_video_path,
            "audio_path": final_audio_path,
            "video_name": final_video_name,
            "audio_name": final_audio_name,
            "trimmed_path": local_trimmed,
            "trimmed_name": unique_trimmed_name,
            "script": script,
            "audio_files": audio_files,
            "gcs_video_uri": f"gs://{bucket_name}/processed/{project_id}/{final_video_name}" if not use_local else None,
            "gcs_audio_uri": f"gs://{bucket_name}/processed/{project_id}/{final_audio_name}" if not use_local else None
        }


