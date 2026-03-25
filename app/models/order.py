from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import OrderSide, OrderType


class Order(BaseModel):
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float = Field(gt=0)
    price: Optional[float] = Field(default=None, gt=0)
    stop_price: Optional[float] = Field(default=None, gt=0)
    reduce_only: bool = False
    client_order_id: Optional[str] = None
