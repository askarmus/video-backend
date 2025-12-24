from typing import Any, Dict
from src.domain.repositories.video_repository import VideoRepository

class UpdateVideoConfigUseCase:
    def __init__(self, video_repo: VideoRepository):
        self.video_repo = video_repo

    def execute(self, video_id: str, user_id: str, config_patch: Dict[str, Any]):
        """
        Lightweight update for video configuration (branding, music, background).
        Does NOT trigger heavy processing.
        """
        # 1. Security: Verify ownership
        video = self.video_repo.get_by_id(video_id)
        if not video:
            raise ValueError(f"Video {video_id} not found")
        
        if video.created_by != user_id:
            raise PermissionError("Unauthorized access to this video configuration")

        # 2. Update via Repository 
        # The repository is already designed to perform a merge on 'video_data'
        updated_video = self.video_repo.update(video_id, video_data=config_patch)
        
        return updated_video.video_data if updated_video else None
