from pydantic import BaseModel
from typing import Optional


class Event(BaseModel):
    source: str
    symbol: Optional[str]
    event_type: str
    direction: Optional[str]
    severity: float
    confidence: float
    timestamp: int
