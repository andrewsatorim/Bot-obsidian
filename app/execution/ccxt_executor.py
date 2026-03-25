from __future__ import annotations

import logging
import time
from typing import Optional

import ccxt.async_support as ccxt_async

from app.models.enums import OrderStatus
from app.models.execution_report import ExecutionReport
from app.models.order import Order
from app.ports.execution_port import ExecutionPort

logger = logging.getLogger(__name__)


class CcxtExecutor(ExecutionPort):
    """Live order execution via ccxt."""

    def __init__(self, exchange_id: str, api_key: str, api_secret: str) -> None:
        config = {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
        }
        exchange_cls = getattr(ccxt_async, exchange_id, None)
        if exchange_cls is None:
            raise ValueError(f"Unknown exchange: {exchange_id}")
        self._exchange: ccxt_async.Exchange = exchange_cls(config)
        self._max_retries = 3

    async def execute(self, order: Order) -> ExecutionReport:
        last_error: Optional[Exception] = None

        for attempt in range(self._max_retries):
            try:
                result = await self._place_order(order)
                return result
            except ccxt_async.RateLimitExceeded:
                wait = 2 ** (attempt + 1)
                logger.warning("rate limited, retrying in %ds (attempt %d/%d)", wait, attempt + 1, self._max_retries)
                import asyncio
                await asyncio.sleep(wait)
            except ccxt_async.NetworkError as e:
                wait = 2 ** (attempt + 1)
                logger.warning("network error: %s, retrying in %ds", e, wait)
                last_error = e
                import asyncio
                await asyncio.sleep(wait)
            except ccxt_async.ExchangeError as e:
                logger.error("exchange error (not retrying): %s", e)
                return ExecutionReport(
                    order_id="",
                    symbol=order.symbol,
                    status=OrderStatus.REJECTED,
                    filled_qty=0.0,
                    avg_price=0.0,
                    fee=0.0,
                )

        logger.error("execution failed after %d retries: %s", self._max_retries, last_error)
        return ExecutionReport(
            order_id="",
            symbol=order.symbol,
            status=OrderStatus.REJECTED,
            filled_qty=0.0,
            avg_price=0.0,
            fee=0.0,
        )

    async def _place_order(self, order: Order) -> ExecutionReport:
        side = order.side.value.lower()
        order_type = order.order_type.value.lower()
        price = order.price if order.order_type.value != "MARKET" else None

        result = await self._exchange.create_order(
            symbol=order.symbol,
            type=order_type,
            side=side,
            amount=order.quantity,
            price=price,
            params={"reduceOnly": order.reduce_only} if order.reduce_only else {},
        )

        order_id = str(result.get("id", ""))
        filled = float(result.get("filled", 0))
        avg_price = float(result.get("average", 0) or result.get("price", 0) or 0)
        fee_info = result.get("fee", {})
        fee = float(fee_info.get("cost", 0)) if fee_info else 0.0

        status_map = {
            "open": OrderStatus.PENDING,
            "closed": OrderStatus.FILLED,
            "canceled": OrderStatus.CANCELLED,
            "expired": OrderStatus.CANCELLED,
        }
        raw_status = result.get("status", "closed")
        status = status_map.get(raw_status, OrderStatus.FILLED)
        if filled > 0 and filled < order.quantity:
            status = OrderStatus.PARTIAL

        report = ExecutionReport(
            order_id=order_id,
            symbol=order.symbol,
            status=status,
            filled_qty=filled,
            avg_price=avg_price,
            fee=fee,
        )
        logger.info("order executed: %s %s %s qty=%.4f filled=%.4f price=%.2f",
                     order_id, side, order.symbol, order.quantity, filled, avg_price)
        return report

    async def close(self) -> None:
        await self._exchange.close()
