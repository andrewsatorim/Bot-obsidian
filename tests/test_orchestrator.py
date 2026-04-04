from __future__ import annotations

from typing import Optional
from dataclasses import dataclass

import pytest

from app.models.feature_vector import FeatureVector
from app.models.market_snapshot import MarketSnapshot
from app.models.order import Order
from app.models.execution_report import ExecutionReport
from app.models.risk_decision import RiskDecision
from app.models.trade_candidate import TradeCandidate
from app.core.orchestrator import Orchestrator
from app.state.state_machine import EngineState


# --- Fakes ---


class FakeDataFeed:
    def __init__(self) -> None:
        self.call_count = 0

    async def get_market_data(self, symbol: str) -> MarketSnapshot:
        self.call_count += 1
        return MarketSnapshot(
            symbol=symbol,
            price=100.0,
            volume_24h=1_000_000.0,
            bid=99.9,
            ask=100.1,
            timestamp=1_000_000,
        )


class FakeAnalytics:
    def build_features(self, market_data: MarketSnapshot) -> FeatureVector:
        return FeatureVector(
            symbol=market_data.symbol,
            atr_proxy=2.0,
            volatility=0.05,
            volume_ratio=1.2,
            funding_zscore=0.0,
            news_score=0.0,
            onchain_score=0.0,
            regime="trending",
        )


class FakeStrategy:
    def __init__(self, signal: Optional[TradeCandidate] = None) -> None:
        self._signal = signal

    def generate_signal(self, features: FeatureVector) -> Optional[TradeCandidate]:
        return self._signal


SAMPLE_SIGNAL = TradeCandidate(
    symbol="BTCUSDT",
    direction="LONG",
    setup_type="breakout",
    entry_price=100.0,
    stop_loss=95.0,
    take_profit=110.0,
    score=0.8,
    expected_value=5.0,
    confidence=0.75,
)


class FakeRisk:
    def __init__(self, allow: bool = True, multiplier: float = 1.0) -> None:
        self._allow = allow
        self._multiplier = multiplier

    def evaluate(self, candidate: TradeCandidate) -> RiskDecision:
        return RiskDecision(
            allow_trade=self._allow,
            risk_multiplier=self._multiplier,
            reason="fake",
        )


class FakeExecution:
    def __init__(self) -> None:
        self.executed_orders: list[Order] = []

    async def execute(self, order: Order) -> ExecutionReport:
        self.executed_orders.append(order)
        return ExecutionReport(
            order_id="fake-001",
            status="FILLED",
            filled_quantity=order.quantity,
            average_price=100.0,
            fee=0.1,
        )


# --- Tests ---


def _make_orchestrator(
    signal: Optional[TradeCandidate] = SAMPLE_SIGNAL,
    allow_trade: bool = True,
    risk_multiplier: float = 1.0,
) -> tuple[Orchestrator, FakeDataFeed, FakeExecution]:
    feed = FakeDataFeed()
    execution = FakeExecution()
    orch = Orchestrator(
        data_feed=feed,
        analytics=FakeAnalytics(),
        strategy=FakeStrategy(signal),
        risk=FakeRisk(allow=allow_trade, multiplier=risk_multiplier),
        execution=execution,
        symbol="BTCUSDT",
    )
    return orch, feed, execution


class TestOrchestratorStepFlow:
    @pytest.mark.asyncio
    async def test_idle_transitions_to_scanning(self) -> None:
        orch, _, _ = _make_orchestrator()
        result = await orch.step()
        assert result is None
        assert orch.state_machine.state == EngineState.SCANNING

    @pytest.mark.asyncio
    async def test_scanning_finds_signal(self) -> None:
        orch, _, _ = _make_orchestrator()
        await orch.step()  # IDLE -> SCANNING
        result = await orch.step()  # SCANNING -> SETUP_FOUND
        assert result is not None
        assert result.symbol == "BTCUSDT"
        assert orch.state_machine.state == EngineState.SETUP_FOUND

    @pytest.mark.asyncio
    async def test_scanning_no_signal_stays(self) -> None:
        orch, _, _ = _make_orchestrator(signal=None)
        await orch.step()  # IDLE -> SCANNING
        result = await orch.step()  # SCANNING, no signal
        assert result is None
        assert orch.state_machine.state == EngineState.SCANNING

    @pytest.mark.asyncio
    async def test_executing_reuses_validated_signal(self) -> None:
        """EXECUTING must not re-fetch market data — it uses the signal from VALIDATING."""
        orch, feed, execution = _make_orchestrator()
        await orch.step()  # IDLE -> SCANNING
        await orch.step()  # SCANNING -> SETUP_FOUND
        await orch.step()  # SETUP_FOUND -> VALIDATING
        await orch.step()  # VALIDATING -> EXECUTING

        calls_before = feed.call_count
        result = await orch.step()  # EXECUTING -> POSITION_OPEN
        calls_after = feed.call_count

        assert calls_after == calls_before  # no extra fetch
        assert result is not None
        assert orch.state_machine.state == EngineState.POSITION_OPEN
        assert len(execution.executed_orders) == 1

    @pytest.mark.asyncio
    async def test_risk_multiplier_applied_to_order(self) -> None:
        orch, _, execution = _make_orchestrator(risk_multiplier=0.5)
        await orch.step()  # IDLE -> SCANNING
        await orch.step()  # SCANNING -> SETUP_FOUND
        await orch.step()  # SETUP_FOUND -> VALIDATING
        await orch.step()  # VALIDATING -> EXECUTING
        await orch.step()  # EXECUTING -> POSITION_OPEN

        assert len(execution.executed_orders) == 1
        assert execution.executed_orders[0].quantity == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_risk_rejection_goes_to_cooldown(self) -> None:
        orch, _, _ = _make_orchestrator(allow_trade=False)
        await orch.step()  # IDLE -> SCANNING
        await orch.step()  # SCANNING -> SETUP_FOUND
        await orch.step()  # SETUP_FOUND -> VALIDATING
        result = await orch.step()  # VALIDATING -> COOLDOWN
        assert result is None
        assert orch.state_machine.state == EngineState.COOLDOWN
