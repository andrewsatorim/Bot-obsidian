from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.enums import RegimeLabel, TrendBias, VolatilityState


class RegimeSnapshot(BaseModel):
    symbol: str
    regime_label: RegimeLabel
    confidence: float = Field(ge=0, le=1)
    trend_bias: TrendBias
    volatility_state: VolatilityState
    allow_reversal_setups: bool = True
    allow_breakout_setups: bool = True
    risk_multiplier: float = Field(default=1.0, gt=0, le=5.0)
