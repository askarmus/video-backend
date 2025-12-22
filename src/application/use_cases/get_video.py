from typing import Optional
from src.domain.entities.video import Video
from src.domain.repositories.video_repository import VideoRepository

class GetVideoByIdUseCase:
    def __init__(self, video_repo: VideoRepository):
        self.video_repo = video_repo

    def execute(self, video_id: str, user_id: str) -> Optional[Video]:
        video = self.video_repo.get_by_id(video_id)
        
        if not video:
            return None
        
        # Access Check: Ensure user is the creator
        if video.created_by != user_id:
            raise PermissionError("User does not have access to this video")
            
        return video
