from __future__ import annotations

from pydantic import BaseModel, Field


class MarketSnapshot(BaseModel):
    symbol: str
    price: float = Field(gt=0)
    volume: float = Field(ge=0)
    bid: float = Field(ge=0)
    ask: float = Field(ge=0)
    timestamp: int = Field(gt=0)
