from __future__ import annotations

import logging
import uuid
from typing import Callable, Optional

from app.models.enums import OrderStatus
from app.models.execution_report import ExecutionReport
from app.models.order import Order
from app.ports.execution_port import ExecutionPort

logger = logging.getLogger(__name__)

FEE_RATE = 0.001  # 0.1%


class PaperExecutor(ExecutionPort):
    """Simulated execution adapter for paper trading."""

    def __init__(self, fill_price: float | None = None) -> None:
        self._fill_price = fill_price
        self._last_known_price: float = 0.0
        self.history: list[ExecutionReport] = []

    def set_price(self, price: float) -> None:
        """Update the current market price for simulated fills."""
        self._last_known_price = price

    async def execute(self, order: Order) -> ExecutionReport:
        order_id = str(uuid.uuid4())[:8]
        price = self._fill_price or self._last_known_price or 1.0
        notional = order.quantity * price
        fee = notional * FEE_RATE

        report = ExecutionReport(
            order_id=order_id,
            symbol=order.symbol,
            status=OrderStatus.FILLED,
            filled_qty=order.quantity,
            avg_price=price,
            fee=fee,
        )
        self.history.append(report)

        logger.info(
            "paper fill: %s %s %s qty=%.4f price=%.2f fee=%.4f",
            order_id, order.side.value, order.symbol,
            order.quantity, price, fee,
        )
        return report
