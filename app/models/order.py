from typing import Optional
from pydantic import BaseModel


class Order(BaseModel):
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    reduce_only: bool = False
    client_order_id: Optional[str] = None
