from __future__ import annotations

from pydantic import BaseModel, Field


class OnChainSnapshot(BaseModel):
    symbol: str
    exchange_inflow: float = Field(ge=0)
    exchange_outflow: float = Field(ge=0)
    whale_activity: float = Field(ge=0)
    mvrv: float
    timestamp: int = Field(gt=0)
