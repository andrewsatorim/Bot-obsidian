from __future__ import annotations

from typing import Optional

from app.models.order import Order
from app.models.trade_candidate import TradeCandidate
from app.models.risk_decision import RiskDecision
from app.ports.analytics_port import AnalyticsPort
from app.ports.data_feed_port import DataFeedPort
from app.ports.execution_port import ExecutionPort
from app.ports.risk_port import RiskPort
from app.ports.strategy_port import StrategyPort
from app.state.state_machine import EngineState, StateMachine


class Orchestrator:
    """Core pipeline that wires data -> features -> strategy -> risk -> execution."""

    BASE_QUANTITY: float = 1.0

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
        state = self.state_machine.state

        if state == EngineState.IDLE:
            self.state_machine.transition(EngineState.SCANNING)
            return None

        if state == EngineState.SCANNING:
            market_data = await self.data_feed.get_market_data(self.symbol)
            features = self.analytics.build_features(market_data)
            signal = self.strategy.generate_signal(features)

            if signal:
                self._pending_signal = signal
                self.state_machine.transition(EngineState.SETUP_FOUND)
                return signal
            return None

        if state == EngineState.SETUP_FOUND:
            self.state_machine.transition(EngineState.VALIDATING)
            return None

        if state == EngineState.VALIDATING:
            market_data = await self.data_feed.get_market_data(self.symbol)
            features = self.analytics.build_features(market_data)
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

        if state == EngineState.POSITION_OPEN:
            self.state_machine.transition(EngineState.SCANNING)
            return None

        if state == EngineState.COOLDOWN:
            self.state_machine.transition(EngineState.SCANNING)
            return None

        return None

    def _build_order(
        self, signal: TradeCandidate, decision: Optional[RiskDecision] = None
    ) -> Order:
        multiplier = decision.risk_multiplier if decision else 1.0
        return Order(
            symbol=signal.symbol,
            side="BUY" if signal.direction == "LONG" else "SELL",
            order_type="MARKET",
            quantity=self.BASE_QUANTITY * multiplier,
        )
