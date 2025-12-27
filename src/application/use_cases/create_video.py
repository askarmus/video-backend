from datetime import datetime
from typing import Any
from src.domain.entities.video import Video
from src.domain.repositories.video_repository import VideoRepository

class CreateVideoUseCase:
    def __init__(self, video_repo: VideoRepository):
        self.video_repo = video_repo

    def execute(self, user_id: str, video_id: str, title: str, video_uri: str, metadata: dict[str, Any], status: str = "processing") -> Video:
        """
        Initializes or updates a video record.
        """
        # 1. Fetch existing video if it exists to preserve documentation
        existing_video = self.video_repo.get_by_id(video_id)
        existing_doc = existing_video.documentation if existing_video else {}

        video_data = {
            "source_video_url": video_uri,
            **(metadata or {})
        }

        video = Video(
            id=video_id,
            created_by=user_id,
            title=title,
            status=status,
            video_data=video_data,
            documentation=existing_doc,
            updated_at=datetime.now()
        )
        
        self.video_repo.save(video)
        return video

