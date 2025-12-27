import os
import uuid
from src.infrastructure.google_client import client, creds
from src.application.pipeline_service import NarrationPipeline


# Setup configurations
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


if __name__ == "__main__":
    env = os.getenv("ENV", "local").lower()
    video_uri = os.getenv("VIDEO_URI")
    
    # 1. Initialize
    from src.infrastructure.repositories.supabase_video_repository import SupabaseVideoRepository
    from src.application.use_cases.create_video import CreateVideoUseCase
    
    repo = SupabaseVideoRepository()
    use_case = CreateVideoUseCase(repo)
    pipeline = NarrationPipeline(gemini_client=client, tts_creds=creds, base_dir=BASE_DIR)

    print(f"\n🚀 STARTING NARRATION WORKFLOW [{env.upper()} MODE]")
    print(f"-" * 45)

    # 2. Preparation (Download)
    # Even in local mode, we need a path. download_video handles exist_ok checks.
    local_raw = pipeline.download_video(video_uri)

    # 3. Core Pipeline
    # We pass the original video_uri for Gemini scripting context
    # Passing valid UUIDs to trigger the DB save logic in pipeline_service
    test_video_id = str(uuid.uuid4())
    test_user_id = "b438b72f-d935-4fba-b3e8-8b2a5ed941b3" # Valid dev user UUID
    results = pipeline.run(

        local_raw, 
        gcs_video_uri=video_uri,
        video_id=test_video_id,
        user_id=test_user_id,
        use_case=use_case
    )



    if results:
        # 4. Success Reporting
        project_id = results.get("project_id", "default")
        
        if env == "prod":
            # In prod mode, the pipeline already uploaded everything to the project folder
            # In prod mode, the pipeline already uploaded everything to the project folder
            final_video_url = results.get("gcs_video_uri", "") 
            final_audio_url = results.get("gcs_audio_uri", "")
        else:
            print(f"⏩ Local assets preserved in: {results['project_dir']}")
            final_video_url = results["video_path"]
            final_audio_url = results["audio_path"]

        print(f"\n✨ FINAL OUTPUTS (Project: {project_id})")
        print(f"🎬 Video: {final_video_url}")
        print(f"🎵 Audio: {final_audio_url}")
        print(f"-" * 45 + "\n")

