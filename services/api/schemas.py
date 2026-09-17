from typing import Optional

from pydantic import BaseModel, Field


class ChatIn(BaseModel):
    session_id: Optional[str] = None
    text: str = Field(..., min_length=2)


class FeedbackIn(BaseModel):
    event_id: int
    rating: int = Field(..., ge=0, le=1)
