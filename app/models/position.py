from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.enums import Direction


class Position(BaseModel):
    symbol: str
    direction: Direction
    size: float = Field(gt=0)
    entry_price: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    unrealized_pnl: float
