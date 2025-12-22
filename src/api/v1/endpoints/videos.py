from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from datetime import datetime
from typing import Optional
import os
import traceback

from src.api.auth import get_current_user
from src.application.use_cases.get_video import GetVideoByIdUseCase
from src.application.use_cases.list_videos import ListVideosUseCase
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

def run_pipeline_background(video_id: str, video_uri: str):
    """
    Background task to execute the video processing pipeline.
    """
    try:
        repo = SupabaseVideoRepository()
        pipeline = NarrationPipeline(gemini_client=client, tts_creds=creds, base_dir=PROJECT_ROOT)

        # 1. Preparation (Download)
        os.environ["VIDEO_URI"] = video_uri
        local_raw = pipeline.download_video(video_uri)

        # 2. Core Pipeline
        results = pipeline.run(local_raw, gcs_video_uri=video_uri)

        if not results:
             print(f"Pipeline processing failed for video {video_id}")
             repo.update(video_id, status="failed")
             return

        # 3. Upload Assets
        final_video_url = pipeline.upload_asset(results["video_path"], f"processed/{results['video_name']}")

        # 4. Update Database
        video_data = {
            "processed_video_url": final_video_url,
            "script": results["script"],
        }

        repo.update(video_id, status="completed", video_data=video_data)
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
    user=Depends(get_current_user)
):
    try:
        repo = SupabaseVideoRepository()
        
        video_data = {
            "source_video_url": request.video_uri,
            "metadata": {
                "file_type": request.file_type,
                "duration": request.duration,
                "user_ip": request.user_ip,
                "user_country": request.user_country,
                "has_intro": False,
                "has_outro": False,
                "is_edited": False,
                "bg_name":"" 
            }
        }
        
        video = Video(
            id=request.video_id,
            created_by=user.id,
            title=request.title,
            status="processing",
            video_data=video_data,
            updated_at=datetime.now()
        )
        
        repo.save(video)

        # Trigger heavy processing in the background
        background_tasks.add_task(run_pipeline_background, request.video_id, request.video_uri)

        return {
            "status": "processing",
            "message": "Video upload acknowledged, processing started in background.",
            "video_id": request.video_id
        }

    except Exception as e:
        print(f"Upload Complete Error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
