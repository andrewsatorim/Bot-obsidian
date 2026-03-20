from pydantic import BaseModel


class NewsImpactReport(BaseModel):
    symbol: str
    bias: str
    severity: float
    confidence: float
    block_long: bool
    block_short: bool
