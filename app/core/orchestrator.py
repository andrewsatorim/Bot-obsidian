from __future__ import annotations

import logging
import time
from typing import Optional

from app.config import Settings
from app.core.exit_manager import ExitAction, ExitConfig, ExitManager
from app.models.enums import Direction, OrderSide, OrderType, SetupType
from app.models.feature_vector import FeatureVector
from app.models.order import Order
from app.models.position import Position
from app.models.signal import Signal
from app.models.trade_candidate import TradeCandidate
from app.ports.analytics_port import AnalyticsPort
from app.ports.data_feed_port import DataFeedPort
from app.ports.execution_port import ExecutionPort
from app.ports.risk_port import RiskPort
from app.ports.strategy_port import StrategyPort
from app.state.state_machine import EngineState, StateMachine

logger = logging.getLogger(__name__)


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
        settings: Settings,
    ) -> None:
        self.data_feed = data_feed
        self.analytics = analytics
        self.strategy = strategy
        self.risk = risk
        self.execution = execution
        self.symbol = symbol
        self.settings = settings

        self.state_machine = StateMachine()

        # Pending state between steps
        self._pending_signal: Optional[Signal] = None
        self._pending_features: Optional[FeatureVector] = None
        self._pending_trade: Optional[TradeCandidate] = None
        self._pending_quantity: float = 0.0
        self._active_position: Optional[Position] = None
        self._exit_manager: Optional[ExitManager] = None
        self._cooldown_until: Optional[float] = None

    async def step(self) -> Optional[TradeCandidate]:
        state = self.state_machine.state

        if state == EngineState.IDLE:
            self.state_machine.transition(EngineState.SCANNING)
            return None

        if state == EngineState.SCANNING:
            return await self._handle_scanning()

        if state == EngineState.SETUP_FOUND:
            return self._handle_setup_found()

        if state == EngineState.VALIDATING:
            return self._handle_validating()

        if state == EngineState.EXECUTING:
            return await self._handle_executing()

        if state == EngineState.POSITION_OPEN:
            return await self._handle_position_open()

        if state == EngineState.COOLDOWN:
            return self._handle_cooldown()

        return None

    # ------------------------------------------------------------------
    # State handlers
    # ------------------------------------------------------------------

    async def _handle_scanning(self) -> Optional[TradeCandidate]:
        try:
            market_data = await self.data_feed.get_market_data(self.symbol)
            features = self.analytics.build_features(market_data)
        except Exception:
            logger.exception("error fetching data in SCANNING")
            return None

        signal = self.strategy.generate_signal(features)

        if signal:
            self._pending_signal = signal
            self._pending_features = features
            self.state_machine.transition(EngineState.SETUP_FOUND)
            logger.info("signal detected: %s %s strength=%.2f", signal.symbol, signal.direction.value, signal.strength)
        return None

    def _handle_setup_found(self) -> Optional[TradeCandidate]:
        if self._pending_signal is None or self._pending_features is None:
            self.state_machine.transition(EngineState.SCANNING)
            return None

        trade = self._build_trade_candidate(self._pending_signal, self._pending_features)
        self._pending_trade = trade
        self.state_machine.transition(EngineState.VALIDATING)
        return None

    def _handle_validating(self) -> Optional[TradeCandidate]:
        if self._pending_trade is None:
            self.state_machine.transition(EngineState.SCANNING)
            return None

        decision = self.risk.evaluate(self._pending_trade)
        logger.info("risk decision: allow=%s multiplier=%.2f reason=%s", decision.allow_trade, decision.risk_multiplier, decision.reason)

        if not decision.allow_trade:
            self._enter_cooldown()
            return None

        self._pending_quantity = self._compute_position_size(
            self._pending_features.atr if self._pending_features else 0.0,
            decision.risk_multiplier,
        )
        self.state_machine.transition(EngineState.EXECUTING)
        return self._pending_trade

    async def _handle_executing(self) -> Optional[TradeCandidate]:
        if self._pending_trade is None:
            self.state_machine.transition(EngineState.SCANNING)
            return None

        order = self._build_order(self._pending_trade, self._pending_quantity)
        try:
            # Update paper executor with current price if applicable
            if hasattr(self.execution, "set_price") and self._pending_trade:
                self.execution.set_price(self._pending_trade.entry_price)
            report = await self.execution.execute(order)
            logger.info("execution: %s %s qty=%.4f avg_price=%.2f", report.status.value, order.symbol, report.filled_qty, report.avg_price)
        except Exception:
            logger.exception("execution failed")
            self._enter_cooldown()
            return None

        self._active_position = Position(
            symbol=self._pending_trade.symbol,
            direction=self._pending_trade.direction,
            size=report.filled_qty,
            entry_price=report.avg_price,
            stop_loss=self._pending_trade.stop_loss,
            unrealized_pnl=0.0,
        )
        # Initialize exit manager for the new position
        atr = self._pending_features.atr if self._pending_features else report.avg_price * 0.01
        self._exit_manager = ExitManager(config=ExitConfig(), atr=atr)

        self.state_machine.transition(EngineState.POSITION_OPEN)

        result = self._pending_trade
        self._pending_signal = None
        self._pending_features = None
        self._pending_trade = None
        return result

    async def _handle_position_open(self) -> Optional[TradeCandidate]:
        if self._active_position is None:
            self.state_machine.transition(EngineState.SCANNING)
            return None

        try:
            market_data = await self.data_feed.get_market_data(self.symbol)
        except Exception:
            logger.exception("error fetching data in POSITION_OPEN")
            return None

        price = market_data.market.price
        pos = self._active_position

        # Update unrealized PnL
        if pos.direction == Direction.LONG:
            pnl = (price - pos.entry_price) * pos.size
        else:
            pnl = (pos.entry_price - price) * pos.size

        self._active_position = pos.model_copy(update={"unrealized_pnl": pnl})

        # Use ExitManager for advanced exit logic
        if self._exit_manager is not None:
            action = self._exit_manager.update(pos, price)

            if action.update_stop_loss is not None:
                self._active_position = pos.model_copy(
                    update={"stop_loss": action.update_stop_loss, "unrealized_pnl": pnl}
                )
                logger.info("stop loss updated to %.2f (%s)", action.update_stop_loss, action.reason)

            if action.close:
                close_qty = action.quantity if action.quantity > 0 else pos.size
                if close_qty >= pos.size:
                    # Full close
                    logger.info("position closed: %s price=%.2f pnl=%.2f reason=%s", pos.symbol, price, pnl, action.reason)
                    order = self._exit_manager.build_close_order(pos)
                    try:
                        await self.execution.execute(order)
                    except Exception:
                        logger.exception("close order failed")
                    self._active_position = None
                    self._exit_manager = None
                    self._enter_cooldown()
                    return None
                else:
                    # Partial close
                    logger.info("partial close: %.4f of %.4f reason=%s", close_qty, pos.size, action.reason)
                    order = self._exit_manager.build_close_order(pos, quantity=close_qty)
                    try:
                        await self.execution.execute(order)
                    except Exception:
                        logger.exception("partial close order failed")
                    remaining = pos.size - close_qty
                    self._active_position = pos.model_copy(update={"size": remaining, "unrealized_pnl": pnl})
        else:
            # Fallback: basic stop loss
            hit_stop = (
                (pos.direction == Direction.LONG and price <= pos.stop_loss)
                or (pos.direction == Direction.SHORT and price >= pos.stop_loss)
            )
            if hit_stop:
                logger.info("stop loss hit: price=%.2f stop=%.2f pnl=%.2f", price, pos.stop_loss, pnl)
                self._active_position = None
                self._enter_cooldown()
                return None

        logger.debug("position open: %s pnl=%.2f price=%.2f", pos.symbol, pnl, price)
        return None

    def _handle_cooldown(self) -> Optional[TradeCandidate]:
        if self._cooldown_until is not None and time.time() < self._cooldown_until:
            return None
        logger.info("cooldown expired, returning to SCANNING")
        self._cooldown_until = None
        self.state_machine.transition(EngineState.SCANNING)
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _enter_cooldown(self) -> None:
        self._cooldown_until = time.time() + self.settings.cooldown_sec
        self.state_machine.transition(EngineState.COOLDOWN)
        self._pending_signal = None
        self._pending_features = None
        self._pending_trade = None
        logger.info("entering cooldown for %.0fs", self.settings.cooldown_sec)

    def _build_trade_candidate(self, signal: Signal, features: FeatureVector) -> TradeCandidate:
        atr = features.atr if features.atr > 0 else features.price * 0.01
        stop_distance = atr * self.settings.atr_risk_multiplier

        if signal.direction == Direction.LONG:
            stop_loss = features.price - stop_distance
            take_profit = features.price + stop_distance * 2.0
        else:
            stop_loss = features.price + stop_distance
            take_profit = features.price - stop_distance * 2.0

        return TradeCandidate(
            symbol=signal.symbol,
            direction=signal.direction,
            setup_type=SetupType.FUNDING_MEAN_REVERSION,
            entry_price=features.price,
            stop_loss=max(stop_loss, 0.01),
            take_profit=max(take_profit, 0.01),
            score=signal.strength,
            expected_value=2.0,
            confidence=signal.strength,
            risk_multiplier=1.0,
        )

    def _compute_position_size(self, atr: float, risk_multiplier: float) -> float:
        equity = self.settings.account_equity
        risk_amount = equity * self.settings.max_position_pct * risk_multiplier
        stop_distance = atr * self.settings.atr_risk_multiplier
        if stop_distance <= 0:
            return risk_amount / max(equity * 0.01, 1.0)
        quantity = risk_amount / stop_distance
        return max(quantity, 0.001)

    def _build_order(self, trade: TradeCandidate, quantity: float) -> Order:
        return Order(
            symbol=trade.symbol,
            side=OrderSide.BUY if trade.direction == Direction.LONG else OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=max(quantity, 0.001),
        )
