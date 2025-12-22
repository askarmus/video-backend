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
        video_data = {
            "source_video_url": video_uri,
            "metadata": metadata
        }
        
        video = Video(
            id=video_id,
            created_by=user_id,
            title=title,
            status=status,
            video_data=video_data,
            updated_at=datetime.now()
        )
        
        self.video_repo.save(video)
        return video

