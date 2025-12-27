from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Body
from typing import Optional, Dict, Any
import os
import traceback

from src.api.auth import get_current_user
from src.application.use_cases.get_video import GetVideoByIdUseCase
from src.application.use_cases.list_videos import ListVideosUseCase
from src.application.use_cases.create_video import CreateVideoUseCase
from src.application.use_cases.update_video_config import UpdateVideoConfigUseCase
from src.application.use_cases.update_video_title import UpdateVideoTitleUseCase
from src.application.use_cases.update_video_guide import UpdateVideoGuideUseCase
from src.infrastructure.repositories.supabase_video_repository import SupabaseVideoRepository
from src.application.pipeline_service import NarrationPipeline
from src.application.document_service import DocumentGenerationService
from src.infrastructure.google_client import client, creds
from src.api.v1.schemas.video import UploadCompleteRequest
from src.domain.entities.video_export import VideoExportStatus, VideoExportJob
from src.infrastructure.repositories.supabase_video_export_repository import SupabaseVideoExportRepository
from src.config import PROJECT_ROOT
import asyncio

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

def update_config_use_case():
    repo = SupabaseVideoRepository()
    return UpdateVideoConfigUseCase(repo)

def update_title_use_case():
    repo = SupabaseVideoRepository()
    return UpdateVideoTitleUseCase(repo)

def update_guide_use_case():
    repo = SupabaseVideoRepository()
    return UpdateVideoGuideUseCase(repo)

def get_export_repo():
    return SupabaseVideoExportRepository()



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

async def simulate_export_process(job_id: str, video_id: str, repo: SupabaseVideoExportRepository):
    """
    Simulates a video export process by updating status and progress over time.
    """
    try:
        # 0. Initial State
        video_repo = SupabaseVideoRepository()
        video_repo.update(video_id, download_ready=False)

        # 1. Processing Stage
        await asyncio.sleep(2)
        repo.update(job_id, status=VideoExportStatus.PROCESSING, progress_percent=10, stage="Analyzing sequence...")
        
        await asyncio.sleep(3)
        repo.update(job_id, progress_percent=35, stage="Rendering frames...")
        
        await asyncio.sleep(4)
        repo.update(job_id, progress_percent=65, stage="Encoding video...")

        # 2. Uploading Stage
        await asyncio.sleep(2)
        repo.update(job_id, status=VideoExportStatus.UPLOADING, progress_percent=80, stage="Uploading to cloud storage...")

        # 3. Finalizing Stage
        await asyncio.sleep(2)
        repo.update(job_id, status=VideoExportStatus.FINALIZING, progress_percent=95, stage="Optimizing for web playback...")

        # 4. Completed
        await asyncio.sleep(1)
        # Simulation output URL
        output_url = "https://storage.googleapis.com/evalsy-storage/2025-12-23%2010-18-18.mp4"
        repo.update(job_id, status=VideoExportStatus.COMPLETED, progress_percent=100, stage="Export complete", output_url=output_url)
        
        # Update main video record
        video_repo = SupabaseVideoRepository()
        v_ent = video_repo.get_by_id(video_id)
        if v_ent:
            v_data = v_ent.video_data or {}
            v_data["last_export_url"] = output_url
            video_repo.update(video_id, download_ready=True, video_data=v_data)
        else:
            video_repo.update(video_id, download_ready=True)

        print(f"🎬 Simulated Export Job {job_id} COMPLETED for video {video_id}.")

    except Exception as e:
        print(f"❌ Export Simulation Error: {e}")
        repo.update(job_id, status=VideoExportStatus.FAILED, error_message=str(e))

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


@router.patch("/{video_id}/settings")
# --- Dynamic Configuration Schema ---
# We use a raw dictionary in the endpoint for maximum flexibility
async def update_video_settings(
    video_id: str,
    config: Dict[str, Any] = Body(..., description="The partial video_data to update/merge"),
    user=Depends(get_current_user),
    use_case: UpdateVideoConfigUseCase = Depends(update_config_use_case)
):
    """
    Update partial fields within video_data (branding, background, music).
    You can pass the full object OR just one single field.
    """
    try:
        if not config:
            raise HTTPException(status_code=400, detail="No config data provided")
            
        use_case.execute(video_id, user.id, config)
        return {"status": "success"}
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        print(f"Update Config API Error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")

@router.patch("/{video_id}/title")
async def update_video_title(
    video_id: str,
    title_data: Dict[str, str] = Body(..., description="The new title for the video"),
    user=Depends(get_current_user),
    use_case: UpdateVideoTitleUseCase = Depends(update_title_use_case)
):
    """
    Update the video title.
    """
    try:
        title = title_data.get("title")
        if not title:
            raise HTTPException(status_code=400, detail="No title provided")
            
        use_case.execute(video_id, user.id, title)
        return {"status": "success", "title": title}
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        print(f"Update Title API Error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/{video_id}/generate-doc")
async def generate_document(
    video_id: str,
    user=Depends(get_current_user)
):
    """
    Generate step-by-step documentation (screenshots) from the video script.
    """
    try:
        repo = SupabaseVideoRepository()
        
        # Verify ownership
        video = repo.get_by_id(video_id)
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        if video.created_by != user.id:
            raise HTTPException(status_code=403, detail="Unauthorized")

        service = DocumentGenerationService(repo, client)
        doc_data = service.generate_guide(video_id)
        
        return {
            "status": "success",
            "message": "Documentation generated successfully",
            "data": doc_data
        }

    except Exception as e:
        print(f"Generate Document Error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{video_id}/guide")
async def update_video_guide(
    video_id: str,
    guide_data: Dict[str, Any] = Body(..., description="The partial documentation/guide data to update"),
    user=Depends(get_current_user),
    use_case: UpdateVideoGuideUseCase = Depends(update_guide_use_case)
):
    """
    Update the video guide/documentation (markdown, steps).
    """
    try:
        if not guide_data:
            raise HTTPException(status_code=400, detail="No guide data provided")
            
        result = use_case.execute(video_id, user.id, guide_data)
        return {"status": "success", "data": result}
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        print(f"Update Guide API Error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/{video_id}/export")
async def start_export(
    video_id: str,
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
    repo: SupabaseVideoExportRepository = Depends(get_export_repo)
):
    """
    Starts a simulated video export job.
    """
    try:
        # 1. Verify video exists and is owned by user
        video_repo = SupabaseVideoRepository()
        video = video_repo.get_by_id(video_id)
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        if video.created_by != user.id:
            raise HTTPException(status_code=403, detail="Unauthorized")

        # 2. Create the job record
        job = VideoExportJob(
            id="", # Let DB or Repo handle it
            video_id=video_id,
            user_id=user.id,
            status=VideoExportStatus.QUEUED,
            progress_percent=0,
            stage="Queuing job..."
        )
        created_job = repo.create(job)
        
        # Reset download_ready immediately for the UI
        video_repo.update(video_id, download_ready=False)

        # 3. Trigger simulation in background
        background_tasks.add_task(simulate_export_process, created_job.id, video_id, repo)

        return {
            "status": "success",
            "message": "Export job started",
            "job": created_job
        }

    except HTTPException: raise
    except Exception as e:
        print(f"Export Start Error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{video_id}/export/status")
async def get_export_status(
    video_id: str,
    user=Depends(get_current_user),
    repo: SupabaseVideoExportRepository = Depends(get_export_repo)
):
    """
    Gets the latest export job for a video.
    """
    try:
        jobs = repo.get_by_video_id(video_id)
        if not jobs:
            return {"status": "none", "job": None}
            
        return {
            "status": "success",
            "job": jobs[0] # Return the most recent one
        }
    except Exception as e:
        print(f"Export Status Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


