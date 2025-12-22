from datetime import datetime
from typing import Any
from src.domain.entities.video import Video
from src.domain.repositories.video_repository import VideoRepository

class CreateVideoUseCase:
    def __init__(self, video_repo: VideoRepository):
        self.video_repo = video_repo

    def execute(self, user_id: str, video_id: str, title: str, video_uri: str, metadata: dict[str, Any]) -> Video:
        """
        Initializes a new video record in the repository with 'processing' status.
        """
        # Ensure metadata has all required fields with defaults
        video_metadata = {
            "file_type": metadata.get("file_type"),
            "duration": metadata.get("duration"),
            "user_ip": metadata.get("user_ip"),
            "user_country": metadata.get("user_country"),
            "has_intro": metadata.get("has_intro", False),
            "has_outro": metadata.get("has_outro", False),
            "is_edited": metadata.get("is_edited", False),
            "bg_name": metadata.get("bg_name", "")
        }

        video_data = {
            "source_video_url": video_uri,
            "metadata": video_metadata
        }
        
        video = Video(
            id=video_id,
            created_by=user_id,
            title=title,
            status="processing",
            video_data=video_data,
            updated_at=datetime.now()
        )
        
        self.video_repo.save(video)
        return video
