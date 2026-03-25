from __future__ import annotations

from pydantic import BaseModel, Field


class RiskDecision(BaseModel):
    allow_trade: bool
    risk_multiplier: float = Field(gt=0, le=5.0)
    reason: str
