from typing import List, Optional
from datetime import datetime, timezone
from src.domain.entities.video_export import VideoExportJob, VideoExportStatus
from src.domain.repositories.video_export_repository import VideoExportRepository
from src.infrastructure.supabase_client import supabase

class SupabaseVideoExportRepository(VideoExportRepository):
    def create(self, job: VideoExportJob) -> VideoExportJob:
        try:
            data = {
                "video_id": job.video_id,
                "user_id": job.user_id,
                "status": job.status.value,
                "progress_percent": job.progress_percent,
                "stage": job.stage,
                "output_url": job.output_url,
                "error_message": job.error_message
            }
            if job.id and len(job.id) > 10: # If UUID provided
                data["id"] = job.id

            res = supabase.table("video_export_jobs").insert(data).execute()
            
            if not res.data:
                raise Exception("Failed to create export job")
            
            inserted = res.data[0]
            return self._map_to_entity(inserted)
        except Exception as e:
            print(f"Export Job Create Error: {e}")
            raise e

    def get_by_id(self, job_id: str) -> Optional[VideoExportJob]:
        try:
            res = supabase.table("video_export_jobs").select("*").eq("id", job_id).single().execute()
            if not res.data:
                return None
            return self._map_to_entity(res.data)
        except Exception as e:
            print(f"Export Job Fetch Error: {e}")
            return None

    def get_by_video_id(self, video_id: str) -> List[VideoExportJob]:
        try:
            res = supabase.table("video_export_jobs").select("*").eq("video_id", video_id).order("created_at", desc=True).execute()
            return [self._map_to_entity(item) for item in res.data or []]
        except Exception as e:
            print(f"Export Job Fetch by Video Error: {e}")
            return []

    def update(self, job_id: str, **kwargs) -> VideoExportJob:
        try:
            payload = {**kwargs}
            if "status" in kwargs and isinstance(kwargs["status"], VideoExportStatus):
                payload["status"] = kwargs["status"].value
            
            payload["updated_at"] = datetime.now(timezone.utc).isoformat()
            
            res = supabase.table("video_export_jobs").update(payload).eq("id", job_id).execute()
            if not res.data:
                raise Exception("Failed to update export job")
            
            return self._map_to_entity(res.data[0])
        except Exception as e:
            print(f"Export Job Update Error: {e}")
            raise e

    def _map_to_entity(self, data: dict) -> VideoExportJob:
        return VideoExportJob(
            id=data["id"],
            video_id=data["video_id"],
            user_id=data["user_id"],
            status=VideoExportStatus(data["status"]),
            progress_percent=data.get("progress_percent", 0),
            stage=data.get("stage"),
            output_url=data.get("output_url"),
            error_message=data.get("error_message"),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at")
        )
