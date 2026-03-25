from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.models.market_snapshot import MarketSnapshot
from app.models.news_impact import NewsImpactReport
from app.models.onchain_snapshot import OnChainSnapshot


class MarketDataBundle(BaseModel):
    market: MarketSnapshot
    price_history: list[float] = Field(min_length=1)
    volume_history: list[float] = Field(min_length=1)
    oi_history: list[float] = Field(default_factory=list)
    funding_history: list[float] = Field(default_factory=list)
    liquidation_above: float = 0.0
    liquidation_below: float = 0.0
    onchain: Optional[OnChainSnapshot] = None
    news: Optional[NewsImpactReport] = None
