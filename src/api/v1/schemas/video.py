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

class TimelineItem(BaseModel):
    id: str
    timestamp: str
    script: Optional[str] = None


class TimelineUpdateRequest(BaseModel):
    video_id: str
    edited_timeline_id: str
    updated_audio_url: str
    updated_timeline: list[TimelineItem]
    time_delta: float

class ScriptUpdate(BaseModel):
    id: str
    voiceover_text: str

class BatchAudioEditRequest(BaseModel):
    video_id: str
    updates: list[ScriptUpdate]
