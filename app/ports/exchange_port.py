from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.models.execution_report import ExecutionReport
from app.models.order import Order
from app.models.position import Position


class ExchangePort(ABC):
    @abstractmethod
    async def place_order(self, order: Order) -> ExecutionReport:
        pass

    @abstractmethod
    async def get_position(self, symbol: str) -> Optional[Position]:
        pass
