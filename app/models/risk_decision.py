from pydantic import BaseModel


class RiskDecision(BaseModel):
    allow_trade: bool
    risk_multiplier: float
    reason: str
