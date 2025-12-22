from abc import ABC, abstractmethod
from typing import Optional
from src.domain.entities.video import Video

class VideoRepository(ABC):
    @abstractmethod
    def get_by_id(self, video_id: str) -> Optional[Video]:
        pass

    @abstractmethod
    def get_all_by_user(self, user_id: str, limit: int = 20) -> list[Video]:
        pass

    @abstractmethod
    def save(self, video: Video) -> Video:
        pass

    @abstractmethod
    def update(self, video_id: str, **kwargs) -> Optional[Video]:
        pass
