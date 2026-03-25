from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import Direction, EventSource


class Event(BaseModel):
    source: EventSource
    symbol: Optional[str] = None
    event_type: str
    direction: Optional[Direction] = None
    severity: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    timestamp: int = Field(gt=0)
