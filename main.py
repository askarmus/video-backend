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
        # 4. Success Reporting
        project_id = results.get("project_id", "default")
        
        if env == "prod":
            # In prod mode, the pipeline already uploaded everything to the project folder
            bucket_name = os.getenv("VIDEO_URI").replace("gs://", "").split("/")[0]
            final_video_url = f"gs://{bucket_name}/processed/{project_id}/{results['video_name']}"
            final_audio_url = f"gs://{bucket_name}/processed/{project_id}/{results['audio_name']}"
        else:
            print(f"⏩ Local assets preserved in: {results['project_dir']}")
            final_video_url = results["video_path"]
            final_audio_url = results["audio_path"]

        print(f"\n✨ FINAL OUTPUTS (Project: {project_id})")
        print(f"🎬 Video: {final_video_url}")
        print(f"🎵 Audio: {final_audio_url}")
        print(f"-" * 45 + "\n")

