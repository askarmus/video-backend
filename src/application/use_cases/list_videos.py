from typing import Any
from src.domain.repositories.video_repository import VideoRepository

class ListVideosUseCase:
    def __init__(self, video_repo: VideoRepository):
        self.video_repo = video_repo

    def execute(self, user_id: str, limit: int = 50):
        # Fetch all videos where user is either the creator 
        # or belongs to the organization that owns the video.
        # The logic is handled in the repository implementation (e.g. Supabase RLS or query).
        videos = self.video_repo.get_all_by_user(user_id, limit)
        
        # Transform to 'Card' representation (only required fields)
        return [
            {
                "id": v.id,
                "title": v.title,
                "thumbnail_url": v.thumbnail_url,
                "status": v.status,
                "created_at": v.created_at
            }
            for v in videos
        ]
