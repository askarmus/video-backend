import json
from datetime import datetime, timezone
from typing import Optional
from src.domain.entities.video import Video
from src.domain.repositories.video_repository import VideoRepository
from src.infrastructure.supabase_client import supabase

class SupabaseVideoRepository(VideoRepository):
    def get_by_id(self, video_id: str) -> Optional[Video]:
        try:
            res = supabase.table("videos").select("*").eq("id", video_id).single().execute()
            if not res.data:
                return None
                
            data = res.data
            
            video_data = data.get("video_data", {})
            if isinstance(video_data, str):
                try: video_data = json.loads(video_data)
                except: video_data = {}

            documentation = data.get("documentation") or {}

            if isinstance(video_data, dict) and "documentation" in video_data:
                del video_data["documentation"]

            if isinstance(documentation, str):
                try: documentation = json.loads(documentation)
                except: documentation = {}

            return Video(
                id=data["id"],
                created_by=data["created_by"],
                video_data=video_data,
                title=data.get("title", "Untitled"),
                language=data.get("language", "en"),
                status=data.get("status", "processing"),
                thumbnail_url=data.get("thumbnail_url"),
                documentation=documentation,
                is_deleted=data.get("is_deleted", False),
                download_ready=data.get("download_ready", False),
                created_at=data.get("created_at"),
                updated_at=data.get("updated_at")
            )
        except Exception as e:
            print(f"Database error: {e}")
            return None

    def get_all_by_user(self, user_id: str, limit: int = 50) -> list[Video]:
        try:
            res = (
                supabase
                .table("videos")
                .select("*")
                .eq("created_by", user_id)
                .eq("is_deleted", False)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )

            videos = []
            for item in res.data or []:
                video_data = item.get("video_data") or {}
                if isinstance(video_data, str):
                    try: video_data = json.loads(video_data)
                    except: video_data = {}

                documentation = item.get("documentation") or {}

                if isinstance(video_data, dict) and "documentation" in video_data:
                    del video_data["documentation"]

                if isinstance(documentation, str):
                    try: documentation = json.loads(documentation)
                    except: documentation = {}

                videos.append(Video(
                    id=item["id"],
                    created_by=item["created_by"],
                    video_data=video_data,
                    title=item.get("title", "Untitled"),
                    language=item.get("language", "en"),
                    status=item.get("status", "processing"),
                    thumbnail_url=item.get("thumbnail_url"),
                    documentation=documentation,
                    is_deleted=item.get("is_deleted", False),
                    download_ready=item.get("download_ready", False),
                    created_at=item.get("created_at"),
                    updated_at=item.get("updated_at")
                ))

            return videos

        except Exception as e:
            print(f"List videos database error: {e}")
            return []

    def save(self, video: Video) -> Video:
        try:
            # Ensure documentation is not nested in video_data during save
            v_data = {**video.video_data}
            if "documentation" in v_data:
                del v_data["documentation"]

            data = {
                "id": video.id,
                "created_by": video.created_by,
                "video_data": v_data,
                "title": video.title,
                "language": video.language,
                "status": video.status,
                "thumbnail_url": video.thumbnail_url,
                "documentation": video.documentation,
                "is_deleted": video.is_deleted,
                "download_ready": video.download_ready,
                "updated_at": video.updated_at.isoformat() if isinstance(video.updated_at, datetime) else video.updated_at
            }
            
            res = supabase.table("videos").upsert(data).execute()
            
            if not res.data:
                raise Exception("Failed to save video to database")
                
            return video
        except Exception as e:
            print(f"Save video database error: {e}")
            raise e


    def update(self, video_id: str, existing_video: Optional[Video] = None, **kwargs) -> Optional[Video]:
        """
        Updates specific fields. 
        Pass 'existing_video' to save a database round-trip.
        """
        try:
            payload = {**kwargs}

            # If updating video_data, perform a top-level merge
            if "video_data" in kwargs:
                video = existing_video or self.get_by_id(video_id)
                if video:
                    current_v_data = video.video_data or {}
                    merged_data = {**current_v_data, **kwargs.get("video_data", {})}
                    # Remove documentation from video_data as it now has its own top-level column
                    if "documentation" in merged_data:
                        del merged_data["documentation"]
                    payload["video_data"] = merged_data

            # If updating documentation, perform a top-level merge
            if "documentation" in kwargs:
                video = existing_video or self.get_by_id(video_id)
                if video and video.documentation:
                    merged_doc = {**video.documentation, **kwargs.get("documentation", {})}
                    payload["documentation"] = merged_doc

            payload["updated_at"] = datetime.now(timezone.utc).isoformat()

            res = (
                supabase
                .table("videos")
                .update(payload)
                .eq("id", video_id)
                .execute()
            )

            if not res.data or len(res.data) == 0:
                return None
                
            # Convert raw result back to Video entity immediately without 3rd fetch
            item = res.data[0]
            v_data = item.get("video_data") or {}
            if isinstance(v_data, str): 
                try: v_data = json.loads(v_data)
                except: v_data = {}
                
            doc_data = item.get("documentation") or {}
            
            if isinstance(v_data, dict) and "documentation" in v_data:
                del v_data["documentation"]

            if isinstance(doc_data, str):
                try: doc_data = json.loads(doc_data)
                except: doc_data = {}

            return Video(
                id=item["id"],
                created_by=item["created_by"],
                video_data=v_data,
                title=item.get("title", "Untitled"),
                language=item.get("language", "en"),
                status=item.get("status", "processing"),
                thumbnail_url=item.get("thumbnail_url"),
                documentation=doc_data,
                is_deleted=item.get("is_deleted", False),
                download_ready=item.get("download_ready", False)
            )

        except Exception as e:
            print(f"Update video repository error: {e}")
            raise
