from pydantic import BaseModel
from typing import Optional

class UploadCompleteRequest(BaseModel):
    video_uri: str
    video_id: str
    title: str = "Untitled Video"
    file_type: Optional[str] = None
    duration: Optional[float] = None
    user_ip: Optional[str] = None
    user_country: Optional[str] = None
