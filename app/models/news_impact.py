from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.enums import NewsBias


class NewsImpactReport(BaseModel):
    symbol: str
    bias: NewsBias
    severity: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    block_long: bool
    block_short: bool
