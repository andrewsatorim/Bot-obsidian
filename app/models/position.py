from pydantic import BaseModel


class Position(BaseModel):
    symbol: str
    direction: str
    size: float
    entry_price: float
    stop_loss: float
    unrealized_pnl: float
