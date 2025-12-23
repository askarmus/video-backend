from fastapi import APIRouter, Depends, HTTPException
import traceback

from src.api.auth import get_current_user
from src.application.use_cases.sync_timeline import SyncTimelineUseCase
from src.infrastructure.repositories.supabase_video_repository import SupabaseVideoRepository
from src.api.v1.schemas.video import BatchAudioEditRequest
from src.infrastructure.google_client import creds

router = APIRouter(prefix="/audio", tags=["Audio"])

def sync_timeline_use_case():
    repo = SupabaseVideoRepository()
    return SyncTimelineUseCase(repo)

 
@router.post("/batch_audio_edit")
async def batch_audio_edit(
    request: BatchAudioEditRequest,
    user=Depends(get_current_user),
    use_case: SyncTimelineUseCase = Depends(sync_timeline_use_case)
):
    try:
        result = use_case.execute_batch(
            video_id=request.video_id,
            user_id=user.id,
            updates=[u.dict() for u in request.updates],
            creds=creds
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        print(f"Batch Audio Edit Error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")
