from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ChatHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    message: str = Field(min_length=1)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    history: Optional[List[ChatHistoryMessage]] = Field(default=None)


class ChatSource(BaseModel):
    project_id: str
    name: str
    score: float


class ChatResponse(BaseModel):
    response: str
    sources: List[ChatSource]
    sources_count: int
    timestamp: datetime
