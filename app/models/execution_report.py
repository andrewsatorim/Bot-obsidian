from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.enums import OrderStatus


class ExecutionReport(BaseModel):
    order_id: str
    symbol: str
    status: OrderStatus
    filled_qty: float = Field(ge=0)
    avg_price: float = Field(ge=0)
    fee: float = Field(ge=0)
