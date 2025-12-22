from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any

@dataclass
class Video:
    id: str
    created_by: str
    video_data: dict[str, Any]
    title: str = "Untitled"
    language: str = "en"
    status: str = "processing"
    thumbnail_url: Optional[str] = None
    is_deleted: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
