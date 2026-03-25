from __future__ import annotations

import pytest

from app.config import Settings
from app.models.enums import Direction, SetupType
from app.models.trade_candidate import TradeCandidate
from app.risk.risk_manager import RiskManager


def _make_trade(**overrides) -> TradeCandidate:
    defaults = dict(
        symbol="BTC/USDT", direction=Direction.LONG,
        setup_type=SetupType.FUNDING_MEAN_REVERSION,
        entry_price=65000.0, stop_loss=64000.0, take_profit=67000.0,
        score=0.7, expected_value=2.0, confidence=0.7,
    )
    defaults.update(overrides)
    return TradeCandidate(**defaults)


@pytest.fixture
def risk(settings):
    return RiskManager(settings)


class TestRiskManager:
    def test_approve_normal(self, risk):
        trade = _make_trade()
        decision = risk.evaluate(trade)
        assert decision.allow_trade is True
        assert decision.risk_multiplier > 0

    def test_reject_daily_loss_limit(self, risk):
        risk.daily_pnl = -10_000.0
        trade = _make_trade()
        decision = risk.evaluate(trade)
        assert decision.allow_trade is False
        assert "daily loss" in decision.reason

    def test_reject_max_positions(self, risk):
        risk.open_positions = 10
        trade = _make_trade()
        decision = risk.evaluate(trade)
        assert decision.allow_trade is False
        assert "positions" in decision.reason

    def test_reject_low_confidence(self, risk):
        trade = _make_trade(confidence=0.1)
        decision = risk.evaluate(trade)
        assert decision.allow_trade is False
        assert "confidence" in decision.reason

    def test_reset_daily(self, risk):
        risk.daily_pnl = -500.0
        risk.reset_daily()
        assert risk.daily_pnl == 0.0

    def test_record_pnl(self, risk):
        risk.record_pnl(100.0)
        risk.record_pnl(-50.0)
        assert risk.daily_pnl == 50.0
