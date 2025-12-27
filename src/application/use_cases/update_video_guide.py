from typing import Any, Dict
from src.domain.repositories.video_repository import VideoRepository
from datetime import datetime, timezone

class UpdateVideoGuideUseCase:
    def __init__(self, video_repo: VideoRepository):
        self.video_repo = video_repo

    def execute(self, video_id: str, user_id: str, guide_data: Dict[str, Any]):
        """
        Updates the guide/documentation content within video_data.
        """
        # 1. Security: Verify ownership
        video = self.video_repo.get_by_id(video_id)
        if not video:
            raise ValueError(f"Video {video_id} not found")
        
        if video.created_by != user_id:
            raise PermissionError("Unauthorized access to this video configuration")

        # 2. Prepare documentation update
        # We need to merge with existing documentation to preserve generated steps if only markdown is updated
        current_doc = video.documentation or {}
        
        # Merge logic
        updated_doc = {**current_doc, **guide_data}
        updated_doc["updated_at"] = datetime.now(timezone.utc).isoformat()

        # 3. Update via Repository
        # We update the top-level documentation field
        use_case_result = self.video_repo.update(
            video_id, 
            existing_video=video, 
            documentation=updated_doc
        )
        
        return use_case_result.documentation if use_case_result else None
