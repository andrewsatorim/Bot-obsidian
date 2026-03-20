from pydantic import BaseModel


class ExecutionReport(BaseModel):
    order_id: str
    symbol: str
    status: str
    filled_qty: float
    avg_price: float
    fee: float
