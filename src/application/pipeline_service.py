import os
import uuid
import time
from datetime import datetime
from src.application.script_service import (
    analyze_video_full_pipeline,
    load_script,
    save_script,
    get_default_project_template
)
from src.infrastructure.voice_service import generate_voiceover
from src.infrastructure.storage_service import download_file, upload_file
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

    # ✅ NEW: explicit narration timeline builder
    def compute_narration_timeline(self, script):
        """
        Adds narration_start and narration_end to each script segment.
        Does NOT remove or redefine existing start_time/end_time.
        This produces an unambiguous narration (audio) timeline for the frontend.
        """
        narration_cursor = 0.0

        for seg in script:
            audio_dur = float(seg.get("audio_duration", 0) or 0)
            pause_dur = float(seg.get("pause_duration", 0) or 0)

            seg["narration_start"] = round(narration_cursor, 3)
            seg["narration_end"] = round(narration_cursor + audio_dur + pause_dur, 3)

            narration_cursor = seg["narration_end"]

        return script

    # ✅ NEW: compute narration duration safely from narration timeline
    def get_narration_duration(self, script):
        """
        Returns total narration duration based on narration_end if present,
        otherwise falls back to sum(audio_duration + pause_duration).
        """
        active = [s for s in script if not s.get("isDeleted", False)]
        if not active:
            return 0.0

        # If narration_end exists, use it
        if all("narration_end" in s for s in active):
            return float(max(s.get("narration_end", 0) for s in active))

        # Fallback: sum durations
        return float(
            sum(
                float(s.get("audio_duration", 0) or 0) + float(s.get("pause_duration", 0) or 0)
                for s in active
            )
        )

    # ✅ NEW: soft validation, never breaks working pipeline
    def validate_narration_timeline(self, script):
        """
        Logs if narration duration mismatches the sum of audio+pause.
        Does not raise, does not break production.
        """
        active = [s for s in script if not s.get("isDeleted", False)]
        if not active:
            return

        expected = sum(
            float(s.get("audio_duration", 0) or 0) + float(s.get("pause_duration", 0) or 0)
            for s in active
        )
        computed = self.get_narration_duration(script)

        if abs(expected - computed) > 0.05:
            print("⚠️ [Timeline] Narration duration mismatch detected")
            print(f"   Expected(sum audio+pause): {expected:.3f}s")
            print(f"   Computed(narration_end):  {computed:.3f}s")
        else:
            print(f"✅ [Timeline] Narration duration validated: {computed:.3f}s")

    def resolve_timeline(self, audio_files, script):
        print(f"⌛ [Timeline] Resolving collisions...")
        next_available = 0.0
        gap = 0.3
        collisions = 0

        for i, seg in enumerate(audio_files):
            audio_duration = self.video_service.get_audio_duration(seg['filename'])

            # Original intended start
            original_start = self._timestamp_to_seconds(seg['timestamp'])

            # Prevent overlap, but DO NOT collapse gaps
            start_time = max(original_start, next_available)

            if start_time > original_start:
                collisions += 1
                new_ts = self._seconds_to_timestamp(start_time)
                seg['timestamp'] = new_ts
                if i < len(script):
                    script[i]['timestamp'] = new_ts

            end_time = start_time + audio_duration

            # Write narration timeline explicitly
            # NOTE: This preserves existing behavior that uses start_time/end_time.
            # The new narration_start/narration_end will be added later without removing anything.
            # Write narration timeline explicitly
            # NOTE: This preserves existing behavior that uses start_time/end_time.
            # The new narration_start/narration_end will be added later without removing anything.
            if i < len(script):
                script[i]["start_time"] = round(start_time, 3)
                script[i]["duration"] = round(audio_duration, 3)
                script[i]["end_time"] = round(end_time, 3)
                script[i]["audio_duration"] = round(audio_duration, 3)
                
                # ✅ NEW: Calculate Word Spans for Karaoke Captions
                # We do this here because we have the EXACT audio_duration from ffprobe
                from src.infrastructure.voice_service import estimate_word_timestamps
                word_spans = estimate_word_timestamps(script[i]["voiceover_text"], audio_duration)
                script[i]["wordSpans"] = word_spans

            next_available = end_time + gap

        if collisions > 0:
            print(f"  ⚠️ Fixed {collisions} overlapping segments.")
        else:
            print(f"  ✅ No audio collisions detected.")

        return audio_files, script

    def download_video(self, gcs_uri):
        """Helper to download a video from GCS"""
        from urllib.parse import urlparse

        bucket_name, blob_name = None, None

        if gcs_uri.startswith("gs://"):
            # gs://bucket/blob
            if "/" in gcs_uri[5:]:
                bucket_name, blob_name = gcs_uri[5:].split("/", 1)
        elif gcs_uri.startswith("http"):
            # https://storage.googleapis.com/bucket/blob
            parsed = urlparse(gcs_uri)
            if "storage.googleapis.com" in parsed.netloc:
                path = parsed.path.lstrip("/")
                if "/" in path:
                    bucket_name, blob_name = path.split("/", 1)

        if not bucket_name or not blob_name:
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
        bucket_name = os.getenv("GCS_BUCKET_NAME", "evalsy-storage")
        return upload_file(bucket_name, local_path, destination_blob)

    def run(self, local_raw_path, gcs_video_uri, video_id=None, user_id=None, title=None, video_uri=None, use_case: CreateVideoUseCase = None):
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
        bucket_name = os.getenv("GCS_BUCKET_NAME", "evalsy-storage")

        # Create project-specific local directory
        project_dir = os.path.join(self.output_dir, project_id)
        voiceovers_dir = os.path.join(project_dir, "voiceovers")
        os.makedirs(voiceovers_dir, exist_ok=True)

        script_file = os.path.join(project_dir, "ai_voiceover_script.json")

        # 1. Initialize Master Envelope
        project_config = get_default_project_template()
        project_config["metadata"]["generated_at"] = timestamp
        project_config["metadata"]["project_id"] = project_id

        # Determine if we are in local mode
        use_local = os.getenv("ENV", "local").lower() == "local"

        # 2. Scripting
        step_start = time.time()
        cleanup_segments = []

        print(f"📝 [2/5] Generating AI Script...")

        analysis_result = analyze_video_full_pipeline(self.client, gcs_video_uri)

        if not analysis_result or "script_timeline" not in analysis_result:
            print("❌ Error: Could not generate script.")
            return None

        script = analysis_result.get("script_timeline", [])
        cleanup_segments = analysis_result.get("cleanup_segments", [])

        # Inject AI results into envelope
        project_config["script"] = script
        project_config["cleanup_segments"] = cleanup_segments

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

        # ✅ FIX: Add explicit narration timeline (contiguous) without removing start_time/end_time
        script = self.compute_narration_timeline(script)

        # ✅ FIX: Validate narration timeline (non-breaking)
        self.validate_narration_timeline(script)

        assemble_start = time.time()
        final_video_name = f"final_{base_name}.mp4"
        final_video_path = os.path.join(project_dir, final_video_name)
        self.video_service.assemble_steps(
            raw_video=local_raw_path,
            script=script,
            audio_files=audio_files,
            output_path=final_video_path,
            cleanup_segments=cleanup_segments
        )
        timings["Video Assembly"] = time.time() - assemble_start

        # Create MP3
        audio_concat_start = time.time()
        final_audio_name = f"narration_{base_name}.mp3"
        final_audio_path = os.path.join(project_dir, final_audio_name)
        self.audio_service.concat_audio_files(audio_files, final_audio_path, project_dir)
        timings["Audio Concat"] = time.time() - audio_concat_start

        # 5. Cloud Upload (All assets in project folder)
        gcs_video_url = None
        gcs_audio_url = None

        if not use_local:
            print(f"☁️  [5/5] Syncing all assets to Cloud Storage...")
            # Upload individual voiceovers
            for i, audio in enumerate(audio_files):
                audio_blob = f"processed/{project_id}/voiceovers/{os.path.basename(audio['filename'])}"
                gcs_url = self.upload_asset(audio['filename'], audio_blob)

                # Update script segment with GCS URL
                if i < len(script):
                    script[i]["audio_url"] = gcs_url
        else:
            # Local mode: assign local paths to audio_url
            for i, audio in enumerate(audio_files):
                if i < len(script):
                    script[i]["audio_url"] = audio["filename"]

        # Keep project_config script updated with final fields
        project_config["script"] = script

        # Save the updated Master Envelope (with IDs, URLs, and calculated times)
        save_script(project_config, script_file)

        # Upload final products
        if not use_local:
            # Capture the public URL returned by upload()
            gcs_video_url = self.upload_asset(final_video_path, f"processed/{project_id}/{final_video_name}")
            gcs_audio_url = self.upload_asset(final_audio_path, f"processed/{project_id}/{final_audio_name}")
            print(f"  ✅ All assets uploaded to GCS folder: processed/{project_id}/")

        # 6. Metadata and Database Update
        if use_case and video_id:
            print(f"💾 Updating database record for video {video_id}...")

            # Fetch final properties
            processed_file_type = os.path.splitext(final_video_path)[1].replace('.', '')
            processed_duration = self.video_service.get_duration(final_video_path)

            # ✅ FIX: narration duration must come from narration timeline, not video timestamps
            narration_end_time = self.get_narration_duration(script)

            metadata = {
                "file_type": processed_file_type,
                "duration": processed_duration,
                "narration_duration": narration_end_time,  # audio/script duration (narration timeline)
                "has_silent_tail": processed_duration > narration_end_time,
                "user_ip": os.getenv("USER_IP", "0.0.0.0"),
                "user_country": os.getenv("USER_COUNTRY", "unknown"),
                "processed_video_url": gcs_video_url or final_video_path,
                # "processed_audio_url": gcs_audio_url or final_audio_path,
                "project_id": project_id,

                # ✅ helpful flag for frontend / debugging, does not break anything
                "timeline_model": "narration_master",

                # Include the full project envelope in the video data
                **project_config
            }

            use_case.execute(
                user_id=user_id or "unknown",
                video_id=video_id,
                title=title or "Untitled",
                video_uri=video_uri or gcs_video_uri,
                metadata=metadata,
                status="completed"
            )

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
            "script": script,
            "audio_files": audio_files,
            "gcs_video_uri": gcs_video_url if not use_local else None,
            "gcs_audio_uri": gcs_audio_url if not use_local else None
        }
