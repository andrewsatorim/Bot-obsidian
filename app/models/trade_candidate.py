from typing import Optional
from pydantic import BaseModel


class TradeCandidate(BaseModel):
    symbol: str
    direction: str
    setup_type: str
    entry_price: float
    stop_loss: float
    take_profit: Optional[float] = None
    score: float
    expected_value: float
    confidence: float
    risk_multiplier: float = 1.0
    venue_hint: Optional[str] = None
    notes: Optional[str] = None
