from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from datetime import datetime
from typing import Optional
import os
import traceback

from src.api.auth import get_current_user
from src.application.use_cases.get_video import GetVideoByIdUseCase
from src.application.use_cases.list_videos import ListVideosUseCase
from src.application.use_cases.create_video import CreateVideoUseCase
from src.application.use_cases.create_video import CreateVideoUseCase
from src.infrastructure.repositories.supabase_video_repository import SupabaseVideoRepository
from src.application.pipeline_service import NarrationPipeline
from src.infrastructure.google_client import client, creds
from src.domain.entities.video import Video
from src.api.v1.schemas.video import UploadCompleteRequest
from src.config import PROJECT_ROOT

router = APIRouter(prefix="/videos", tags=["Videos"])

# Wire up the dependencies
def get_video_use_case():
    repo = SupabaseVideoRepository()
    return GetVideoByIdUseCase(repo)

def list_videos_use_case():
    repo = SupabaseVideoRepository()
    return ListVideosUseCase(repo)

def create_video_use_case():
    repo = SupabaseVideoRepository()
    return CreateVideoUseCase(repo)



def run_pipeline_background(video_id: str, video_uri: str, user_id: str, title: str, user_ip: str = "0.0.0.0", user_country: str = "unknown"):
    """
    Background task to execute the video processing pipeline.
    """
    try:
        # Set environment variables for the pipeline to consume
        os.environ["VIDEO_URI"] = video_uri
        os.environ["USER_IP"] = user_ip
        os.environ["USER_COUNTRY"] = user_country
        repo = SupabaseVideoRepository()
        use_case = CreateVideoUseCase(repo)
        pipeline = NarrationPipeline(gemini_client=client, tts_creds=creds, base_dir=PROJECT_ROOT)


        # 1. Preparation (Download)
        os.environ["VIDEO_URI"] = video_uri
        local_raw = pipeline.download_video(video_uri)

        # 2. Core Pipeline - Now handles DB updates internally
        results = pipeline.run(
            local_raw_path=local_raw, 
            gcs_video_uri=video_uri,
            video_id=video_id,
            user_id=user_id,
            title=title,
            video_uri=video_uri,
            use_case=use_case
        )

        if not results:
             print(f"Pipeline processing failed for video {video_id}")
             repo.update(video_id, status="failed")
             return

        print(f"Background processing complete for video {video_id}")


    except Exception as e:
        print(f"Background Processing Error for {video_id}: {e}")
        traceback.print_exc()
        try:
            repo = SupabaseVideoRepository()
            repo.update(video_id, status="failed")
        except:
            pass

@router.get("/")
async def list_videos(
    user=Depends(get_current_user),
    use_case: ListVideosUseCase = Depends(list_videos_use_case)
):
    try:
        return use_case.execute(user.id)
    except Exception as e:
        print(f"API Error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/{video_id}")
async def get_video(
    video_id: str, 
    user=Depends(get_current_user),
    use_case: GetVideoByIdUseCase = Depends(get_video_use_case)
):
    try:
        video = use_case.execute(video_id, user.id)
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        return video
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        print(f"API Error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/upload_complete")
async def upload_complete(
    request: UploadCompleteRequest, 
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
    use_case: CreateVideoUseCase = Depends(create_video_use_case)
):
    try:
        # Use common Use Case to initialize video record
        metadata = {
            "file_type": request.file_type,
            "duration": request.duration,
            "user_ip": request.user_ip,
            "user_country": request.user_country
        }
        
        use_case.execute(
            user_id=user.id,
            video_id=request.video_id,
            title=request.title,
            video_uri=request.video_uri,
            metadata=metadata
        )

        # Trigger heavy processing in the background
        background_tasks.add_task(
            run_pipeline_background, 
            request.video_id, 
            request.video_uri, 
            user.id, 
            request.title,
            request.user_ip,
            request.user_country
        )

        return {
            "status": "processing",
            "message": "Video upload acknowledged, processing started in background.",
            "video_id": request.video_id
        }

    except Exception as e:
        print(f"Upload Complete Error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


