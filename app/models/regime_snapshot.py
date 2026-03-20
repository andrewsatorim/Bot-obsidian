from pydantic import BaseModel


class RegimeSnapshot(BaseModel):
    symbol: str
    regime_label: str
    confidence: float
    trend_bias: str
    volatility_state: str
    allow_reversal_setups: bool = True
    allow_breakout_setups: bool = True
    risk_multiplier: float = 1.0
