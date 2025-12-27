from abc import ABC, abstractmethod
from typing import List, Optional
from src.domain.entities.video_export import VideoExportJob

class VideoExportRepository(ABC):
    @abstractmethod
    def create(self, job: VideoExportJob) -> VideoExportJob:
        pass

    @abstractmethod
    def get_by_id(self, job_id: str) -> Optional[VideoExportJob]:
        pass

    @abstractmethod
    def get_by_video_id(self, video_id: str) -> List[VideoExportJob]:
        pass

    @abstractmethod
    def update(self, job_id: str, **kwargs) -> VideoExportJob:
        pass
