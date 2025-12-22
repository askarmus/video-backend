import os
from src.infrastructure.google_client import client, creds
from src.application.pipeline_service import NarrationPipeline

# Setup configurations
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


if __name__ == "__main__":
    env = os.getenv("ENV", "local").lower()
    video_uri = os.getenv("VIDEO_URI")
    
    # 1. Initialize
    pipeline = NarrationPipeline(gemini_client=client, tts_creds=creds, base_dir=BASE_DIR)

    print(f"\n🚀 STARTING NARRATION WORKFLOW [{env.upper()} MODE]")
    print(f"-" * 45)

    # 2. Preparation (Download)
    # Even in local mode, we need a path. download_video handles exist_ok checks.
    local_raw = pipeline.download_video(video_uri)

    # 3. Core Pipeline
    # We pass the original video_uri for Gemini scripting context
    results = pipeline.run(local_raw, gcs_video_uri=video_uri)

    if results:
        # 4. Cloud Sync (Optional)
        if env == "prod":
            print(f"☁️  Uploading results to cloud...")
            final_video_url = pipeline.upload_asset(results["video_path"], f"processed/{results['video_name']}")
            final_audio_url = pipeline.upload_asset(results["audio_path"], f"processed/{results['audio_name']}")
        else:
            print(f"⏩ Skipping upload (Local Mode)")
            final_video_url = results["video_path"]
            final_audio_url = results["audio_path"]

        print(f"\n✨ FINAL OUTPUTS:")
        print(f"🎬 Video: {final_video_url}")
        print(f"🎵 Audio: {final_audio_url}")
        print(f"-" * 45 + "\n")
