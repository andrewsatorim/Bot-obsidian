from __future__ import annotations

import pytest

from app.analytics.feature_engine import FeatureEngine
from app.config import Settings
from app.core.orchestrator import Orchestrator
from app.execution.paper_executor import PaperExecutor
from app.feeds.simulated_feed import SimulatedDataFeed
from app.risk.risk_manager import RiskManager
from app.state.state_machine import EngineState
from app.strategy.funding_mean_reversion import FundingMeanReversionStrategy


@pytest.fixture
def orchestrator(settings):
    return Orchestrator(
        data_feed=SimulatedDataFeed(),
        analytics=FeatureEngine(),
        strategy=FundingMeanReversionStrategy(symbol=settings.symbol),
        risk=RiskManager(settings),
        execution=PaperExecutor(),
        symbol=settings.symbol,
        settings=settings,
    )


class TestOrchestrator:
    @pytest.mark.asyncio
    async def test_idle_to_scanning(self, orchestrator):
        assert orchestrator.state_machine.state == EngineState.IDLE
        await orchestrator.step()
        assert orchestrator.state_machine.state == EngineState.SCANNING

    @pytest.mark.asyncio
    async def test_scanning_stays_or_advances(self, orchestrator):
        await orchestrator.step()  # IDLE -> SCANNING
        await orchestrator.step()  # SCANNING -> depends on signal
        state = orchestrator.state_machine.state
        assert state in (EngineState.SCANNING, EngineState.SETUP_FOUND)

    @pytest.mark.asyncio
    async def test_cooldown_has_timer(self, orchestrator):
        orchestrator.state_machine.transition(EngineState.SCANNING)
        orchestrator._enter_cooldown()
        assert orchestrator.state_machine.state == EngineState.COOLDOWN
        assert orchestrator._cooldown_until is not None

        # Should stay in cooldown (timer not expired)
        await orchestrator.step()
        assert orchestrator.state_machine.state == EngineState.COOLDOWN

    @pytest.mark.asyncio
    async def test_multiple_steps_no_crash(self, orchestrator):
        for _ in range(20):
            await orchestrator.step()

    @pytest.mark.asyncio
    async def test_pending_cleared_on_cooldown(self, orchestrator):
        orchestrator.state_machine.transition(EngineState.SCANNING)
        orchestrator._enter_cooldown()
        assert orchestrator._pending_signal is None
        assert orchestrator._pending_trade is None
