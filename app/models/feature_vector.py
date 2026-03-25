from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.enums import RegimeLabel


class FeatureVector(BaseModel):
    price: float = Field(ge=0)
    atr: float = Field(ge=0)
    volatility_regime: float

    volume_ratio: float
    volume_spike: bool

    oi_delta: float
    oi_trend: float

    funding: float
    funding_zscore: float

    spread: float = Field(ge=0)
    slippage_estimate: float = Field(ge=0)

    liquidation_above: float
    liquidation_below: float

    news_score: float
    onchain_score: float

    regime_label: RegimeLabel
