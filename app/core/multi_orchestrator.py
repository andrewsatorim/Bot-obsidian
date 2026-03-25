from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.config import Settings
from app.core.orchestrator import Orchestrator
from app.models.trade_candidate import TradeCandidate
from app.ports.analytics_port import AnalyticsPort
from app.ports.data_feed_port import DataFeedPort
from app.ports.execution_port import ExecutionPort
from app.ports.risk_port import RiskPort
from app.ports.strategy_port import StrategyPort

logger = logging.getLogger(__name__)


class MultiOrchestrator:
    """Manages multiple Orchestrator instances for multi-symbol trading.

    Features:
    - Independent orchestrators per symbol
    - Portfolio-level correlation check
    - Aggregate position tracking
    """

    def __init__(
        self,
        symbols: list[str],
        data_feed_factory: type,
        analytics: AnalyticsPort,
        strategy_factory: type,
        risk: RiskPort,
        execution: ExecutionPort,
        settings: Settings,
        max_correlated_positions: int = 2,
    ) -> None:
        self._orchestrators: dict[str, Orchestrator] = {}
        self._max_correlated = max_correlated_positions

        for symbol in symbols:
            data_feed = data_feed_factory()
            strategy = strategy_factory(symbol=symbol)
            orch = Orchestrator(
                data_feed=data_feed,
                analytics=analytics,
                strategy=strategy,
                risk=risk,
                execution=execution,
                symbol=symbol,
                settings=settings,
            )
            self._orchestrators[symbol] = orch
            logger.info("registered orchestrator for %s", symbol)

    @property
    def symbols(self) -> list[str]:
        return list(self._orchestrators.keys())

    @property
    def active_positions_count(self) -> int:
        return sum(
            1 for o in self._orchestrators.values()
            if o._active_position is not None
        )

    async def step(self) -> dict[str, Optional[TradeCandidate]]:
        """Run one step for all symbols concurrently."""
        tasks = {}
        for symbol, orch in self._orchestrators.items():
            # Portfolio-level guard: limit total active positions
            if self.active_positions_count >= self._max_correlated:
                if orch._active_position is None and orch.state_machine.state.value not in ("POSITION_OPEN", "COOLDOWN"):
                    logger.debug("skipping %s: portfolio position limit reached", symbol)
                    continue
            tasks[symbol] = asyncio.create_task(orch.step())

        results: dict[str, Optional[TradeCandidate]] = {}
        for symbol, task in tasks.items():
            try:
                results[symbol] = await task
            except Exception:
                logger.exception("error stepping %s", symbol)
                results[symbol] = None

        return results

    def get_orchestrator(self, symbol: str) -> Optional[Orchestrator]:
        return self._orchestrators.get(symbol)

    def halt_all(self) -> None:
        from app.state.state_machine import EngineState
        for symbol, orch in self._orchestrators.items():
            if orch.state_machine.can_transition(EngineState.HALTED):
                orch.state_machine.transition(EngineState.HALTED)
                logger.info("halted %s", symbol)
