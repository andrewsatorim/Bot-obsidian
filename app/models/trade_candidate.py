from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import Direction, SetupType


class TradeCandidate(BaseModel):
    symbol: str
    direction: Direction
    setup_type: SetupType
    entry_price: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    take_profit: Optional[float] = Field(default=None, gt=0)
    score: float = Field(ge=0, le=1)
    expected_value: float
    confidence: float = Field(ge=0, le=1)
    risk_multiplier: float = Field(default=1.0, gt=0, le=5.0)
    venue_hint: Optional[str] = None
    notes: Optional[str] = None
