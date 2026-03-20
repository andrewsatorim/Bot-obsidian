from pydantic import BaseModel


class MarketSnapshot(BaseModel):
    symbol: str
    price: float
    volume: float
    bid: float
    ask: float
    timestamp: int
