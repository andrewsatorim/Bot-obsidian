from __future__ import annotations

import pytest

from app.execution.paper_executor import PaperExecutor
from app.models.enums import OrderSide, OrderStatus, OrderType
from app.models.order import Order


@pytest.fixture
def executor():
    return PaperExecutor(fill_price=65000.0)


class TestPaperExecutor:
    @pytest.mark.asyncio
    async def test_execute_returns_filled(self, executor):
        order = Order(symbol="BTC", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1.0)
        report = await executor.execute(order)
        assert report.status == OrderStatus.FILLED
        assert report.filled_qty == 1.0
        assert report.avg_price == 65000.0

    @pytest.mark.asyncio
    async def test_fee_calculation(self, executor):
        order = Order(symbol="BTC", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1.0)
        report = await executor.execute(order)
        expected_fee = 1.0 * 65000.0 * 0.001
        assert report.fee == pytest.approx(expected_fee)

    @pytest.mark.asyncio
    async def test_history_accumulates(self, executor):
        order = Order(symbol="BTC", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=0.5)
        await executor.execute(order)
        await executor.execute(order)
        assert len(executor.history) == 2

    @pytest.mark.asyncio
    async def test_unique_order_ids(self, executor):
        order = Order(symbol="BTC", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1.0)
        r1 = await executor.execute(order)
        r2 = await executor.execute(order)
        assert r1.order_id != r2.order_id
