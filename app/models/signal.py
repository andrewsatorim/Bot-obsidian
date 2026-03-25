from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.enums import Direction


class Signal(BaseModel):
    symbol: str
    direction: Direction
    strength: float = Field(ge=0.0, le=1.0)
    timestamp: int = Field(gt=0)
