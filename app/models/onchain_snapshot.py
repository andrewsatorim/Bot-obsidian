from pydantic import BaseModel


class OnChainSnapshot(BaseModel):
    symbol: str
    exchange_inflow: float
    exchange_outflow: float
    whale_activity: float
    mvrv: float
    timestamp: int
