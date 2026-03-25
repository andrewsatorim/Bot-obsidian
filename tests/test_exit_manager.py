from __future__ import annotations

import pytest

from app.core.exit_manager import ExitConfig, ExitManager
from app.models.enums import Direction
from app.models.position import Position


def _pos(direction: Direction = Direction.LONG, entry: float = 100.0, sl: float = 90.0) -> Position:
    return Position(
        symbol="BTC/USDT", direction=direction,
        size=1.0, entry_price=entry, stop_loss=sl, unrealized_pnl=0.0,
    )


class TestExitManager:
    def test_hold_when_no_trigger(self):
        em = ExitManager(ExitConfig(), atr=5.0)
        pos = _pos()
        action = em.update(pos, 101.0)
        assert action.close is False
        assert action.reason == "hold"

    def test_stop_loss_long(self):
        em = ExitManager(ExitConfig(), atr=5.0)
        pos = _pos(direction=Direction.LONG, entry=100.0, sl=95.0)
        action = em.update(pos, 94.0)
        assert action.close is True
        assert action.reason == "stop_loss"

    def test_stop_loss_short(self):
        em = ExitManager(ExitConfig(), atr=5.0)
        pos = _pos(direction=Direction.SHORT, entry=100.0, sl=105.0)
        action = em.update(pos, 106.0)
        assert action.close is True
        assert action.reason == "stop_loss"

    def test_breakeven_trigger(self):
        config = ExitConfig(breakeven_atr=1.0)
        em = ExitManager(config, atr=5.0)
        pos = _pos(direction=Direction.LONG, entry=100.0, sl=90.0)
        # Price moves +5 (1 ATR) -> breakeven
        action = em.update(pos, 105.0)
        assert action.update_stop_loss == 100.0
        assert action.reason == "breakeven"

    def test_partial_close(self):
        config = ExitConfig(partial_close_atr=2.0, partial_close_pct=0.5, breakeven_atr=0)
        em = ExitManager(config, atr=5.0)
        pos = _pos(direction=Direction.LONG, entry=100.0, sl=90.0)
        # Price moves +10 (2 ATR) -> partial close
        action = em.update(pos, 110.0)
        assert action.close is True
        assert action.quantity == 0.5
        assert action.reason == "partial_take_profit"

    def test_trailing_stop_long(self):
        config = ExitConfig(trailing_stop_atr=1.0, breakeven_atr=0, partial_close_atr=0)
        em = ExitManager(config, atr=5.0)
        pos = _pos(direction=Direction.LONG, entry=100.0, sl=90.0)
        # Price goes up
        em.update(pos, 115.0)
        # Price drops back — trailing stop at 115 - 5 = 110
        action = em.update(pos, 109.0)
        assert action.close is True
        assert action.reason == "trailing_stop"

    def test_time_exit(self):
        config = ExitConfig(time_exit_bars=3, breakeven_atr=0, partial_close_atr=0)
        em = ExitManager(config, atr=5.0)
        pos = _pos()
        em.update(pos, 101.0)
        em.update(pos, 102.0)
        action = em.update(pos, 103.0)
        assert action.close is True
        assert action.reason == "time_exit"

    def test_build_close_order(self):
        em = ExitManager(ExitConfig(), atr=5.0)
        pos = _pos(direction=Direction.LONG)
        order = em.build_close_order(pos)
        assert order.side.value == "SELL"
        assert order.reduce_only is True
        assert order.quantity == pos.size
