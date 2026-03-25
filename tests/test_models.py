from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.enums import Direction, NewsBias, OrderSide, OrderStatus, OrderType, RegimeLabel
from app.models.execution_report import ExecutionReport
from app.models.market_snapshot import MarketSnapshot
from app.models.order import Order
from app.models.position import Position
from app.models.signal import Signal
from app.models.trade_candidate import TradeCandidate


class TestSignal:
    def test_valid_signal(self):
        s = Signal(symbol="BTC", direction=Direction.LONG, strength=0.5, timestamp=1000)
        assert s.direction == Direction.LONG

    def test_invalid_direction(self):
        with pytest.raises(ValidationError):
            Signal(symbol="BTC", direction="INVALID", strength=0.5, timestamp=1000)

    def test_strength_out_of_range(self):
        with pytest.raises(ValidationError):
            Signal(symbol="BTC", direction=Direction.LONG, strength=1.5, timestamp=1000)

    def test_negative_strength(self):
        with pytest.raises(ValidationError):
            Signal(symbol="BTC", direction=Direction.LONG, strength=-0.1, timestamp=1000)


class TestOrder:
    def test_valid_order(self):
        o = Order(symbol="BTC", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1.0)
        assert o.side == OrderSide.BUY

    def test_negative_quantity(self):
        with pytest.raises(ValidationError):
            Order(symbol="BTC", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=-1.0)

    def test_zero_quantity(self):
        with pytest.raises(ValidationError):
            Order(symbol="BTC", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=0.0)


class TestMarketSnapshot:
    def test_valid_snapshot(self):
        ms = MarketSnapshot(symbol="BTC", price=100.0, volume=50.0, bid=99.0, ask=101.0, timestamp=1)
        assert ms.price == 100.0

    def test_negative_price(self):
        with pytest.raises(ValidationError):
            MarketSnapshot(symbol="BTC", price=-1.0, volume=50.0, bid=99.0, ask=101.0, timestamp=1)

    def test_zero_price(self):
        with pytest.raises(ValidationError):
            MarketSnapshot(symbol="BTC", price=0.0, volume=50.0, bid=99.0, ask=101.0, timestamp=1)


class TestPosition:
    def test_valid_position(self):
        p = Position(symbol="BTC", direction=Direction.LONG, size=1.0, entry_price=100.0, stop_loss=90.0, unrealized_pnl=10.0)
        assert p.direction == Direction.LONG

    def test_invalid_direction(self):
        with pytest.raises(ValidationError):
            Position(symbol="BTC", direction="UP", size=1.0, entry_price=100.0, stop_loss=90.0, unrealized_pnl=0.0)


class TestExecutionReport:
    def test_valid_report(self):
        r = ExecutionReport(order_id="123", symbol="BTC", status=OrderStatus.FILLED, filled_qty=1.0, avg_price=100.0, fee=0.1)
        assert r.status == OrderStatus.FILLED

    def test_negative_fee(self):
        with pytest.raises(ValidationError):
            ExecutionReport(order_id="123", symbol="BTC", status=OrderStatus.FILLED, filled_qty=1.0, avg_price=100.0, fee=-0.1)
