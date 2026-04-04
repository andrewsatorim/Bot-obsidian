from __future__ import annotations

from typing import Optional
from typing_extensions import TypedDict

from app.models.market_snapshot import MarketSnapshot
from app.models.news_impact import NewsImpactReport
from app.models.onchain_snapshot import OnChainSnapshot


class MarketBundle(TypedDict, total=False):
    """Full market data bundle passed from a DataFeed adapter to FeatureEngine.

    Only `market` is required. All other fields default to empty/zero when absent,
    allowing adapters to supply only the data sources they have access to.
    """

    market: MarketSnapshot          # required
    price_history: list[float]
    volume_history: list[float]
    oi_history: list[float]
    funding_history: list[float]
    liquidation_above: float
    liquidation_below: float
    onchain: Optional[OnChainSnapshot]
    news: Optional[NewsImpactReport]
