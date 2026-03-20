from pydantic import BaseModel


class FeatureVector(BaseModel):
    price: float
    atr: float
    volatility_regime: float

    volume_ratio: float
    volume_spike: bool

    oi_delta: float
    oi_trend: float

    funding: float
    funding_zscore: float

    spread: float
    slippage_estimate: float

    liquidation_above: float
    liquidation_below: float

    news_score: float
    onchain_score: float

    regime_label: str
