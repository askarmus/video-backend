from src.domain.repositories.video_repository import VideoRepository

class UpdateVideoTitleUseCase:
    def __init__(self, video_repo: VideoRepository):
        self.video_repo = video_repo

    def execute(self, video_id: str, user_id: str, title: str):
        """
        Updates the video title.
        """
        # 1. Security: Verify ownership
        video = self.video_repo.get_by_id(video_id)
        if not video:
            raise ValueError(f"Video {video_id} not found")
        
        if video.created_by != user_id:
            raise PermissionError("Unauthorized access to this video")

        # 2. Update via Repository
        updated_video = self.video_repo.update(video_id, existing_video=video, title=title)
        
        return updated_video
