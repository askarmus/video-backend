from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

class VideoExportStatus(str, Enum):
    QUEUED = 'queued'
    PROCESSING = 'processing'
    UPLOADING = 'uploading'
    FINALIZING = 'finalizing'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'

@dataclass
class VideoExportJob:
    id: str
    video_id: str
    user_id: str
    status: VideoExportStatus
    progress_percent: int = 0
    stage: Optional[str] = None
    output_url: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
