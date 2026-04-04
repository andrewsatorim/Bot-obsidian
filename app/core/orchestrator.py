from __future__ import annotations

from typing import Optional

from app.models.order import Order
from app.models.risk_decision import RiskDecision
from app.models.trade_candidate import TradeCandidate
from app.ports.analytics_port import AnalyticsPort
from app.ports.data_feed_port import DataFeedPort
from app.ports.execution_port import ExecutionPort
from app.ports.risk_port import RiskPort
from app.ports.strategy_port import StrategyPort
from app.state.state_machine import EngineState, StateMachine


class Orchestrator:
    """Core pipeline that wires data -> features -> strategy -> risk -> execution."""

    def __init__(
        self,
        data_feed: DataFeedPort,
        analytics: AnalyticsPort,
        strategy: StrategyPort,
        risk: RiskPort,
        execution: ExecutionPort,
        symbol: str,
    ) -> None:
        self.data_feed = data_feed
        self.analytics = analytics
        self.strategy = strategy
        self.risk = risk
        self.execution = execution
        self.symbol = symbol

        self.state_machine = StateMachine()
        self._pending_signal: Optional[TradeCandidate] = None
        self._pending_risk: Optional[RiskDecision] = None

    async def step(self) -> Optional[TradeCandidate]:
        """Advance the engine by one tick.

        Data is fetched and features are built exactly once per call, then
        passed through the state handler so all decisions within a single tick
        operate on the same market snapshot.
        """
        state = self.state_machine.state

        # States that do not need market data
        if state == EngineState.IDLE:
            self.state_machine.transition(EngineState.SCANNING)
            return None

        if state == EngineState.SETUP_FOUND:
            self.state_machine.transition(EngineState.VALIDATING)
            return None

        if state == EngineState.POSITION_OPEN:
            self.state_machine.transition(EngineState.SCANNING)
            return None

        if state == EngineState.COOLDOWN:
            self.state_machine.transition(EngineState.SCANNING)
            return None

        # EXECUTING reuses the validated signal — no re-fetch needed
        if state == EngineState.EXECUTING:
            signal = self._pending_signal
            decision = self._pending_risk

            if not signal:
                self.state_machine.transition(EngineState.SCANNING)
                return None

            order = self._build_order(signal, decision)
            await self.execution.execute(order)

            self._pending_signal = None
            self._pending_risk = None
            self.state_machine.transition(EngineState.POSITION_OPEN)
            return signal

        # States that require a market snapshot — fetch once
        market_data = await self.data_feed.get_market_data(self.symbol)
        features = self.analytics.build_features(market_data)

        if state == EngineState.SCANNING:
            signal = self.strategy.generate_signal(features)
            if signal:
                self._pending_signal = signal
                self.state_machine.transition(EngineState.SETUP_FOUND)
                return signal
            return None

        if state == EngineState.VALIDATING:
            signal = self.strategy.generate_signal(features)
            if not signal:
                self._pending_signal = None
                self.state_machine.transition(EngineState.SCANNING)
                return None

            self._pending_signal = signal
            decision: RiskDecision = self.risk.evaluate(signal)
            if not decision.allow_trade:
                self._pending_signal = None
                self._pending_risk = None
                self.state_machine.transition(EngineState.COOLDOWN)
                return None

            self._pending_risk = decision
            self.state_machine.transition(EngineState.EXECUTING)
            return signal

        return None

    def _build_order(self, signal: TradeCandidate, decision: Optional[RiskDecision] = None) -> Order:
        """Build an order from a validated signal and risk decision.

        Quantity is derived from the signal's base risk_multiplier scaled by
        the risk layer's multiplier.
        """
        risk_mult = decision.risk_multiplier if decision else 1.0
        quantity = signal.risk_multiplier * risk_mult
        return Order(
            symbol=signal.symbol,
            side="BUY" if signal.direction == "LONG" else "SELL",
            order_type="MARKET",
            quantity=quantity,
        )
