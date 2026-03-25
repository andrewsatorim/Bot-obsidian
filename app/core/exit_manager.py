from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from app.models.enums import Direction, OrderSide, OrderType
from app.models.order import Order
from app.models.position import Position

logger = logging.getLogger(__name__)


@dataclass
class ExitConfig:
    trailing_stop_atr: float = 2.0      # Trailing stop distance in ATR units
    breakeven_atr: float = 1.0           # Move SL to entry after +N ATR
    partial_close_atr: float = 2.0       # Close 50% at +N ATR
    partial_close_pct: float = 0.5       # Fraction to close
    time_exit_bars: int = 0              # Close after N bars (0 = disabled)
    funding_exit_threshold: float = 0.0  # Close if funding cost exceeds this


class ExitManager:
    """Manages position exits: trailing stop, partial close, breakeven, time-based."""

    def __init__(self, config: ExitConfig, atr: float) -> None:
        self.config = config
        self.atr = atr if atr > 0 else 1.0
        self._highest_price: Optional[float] = None
        self._lowest_price: Optional[float] = None
        self._partial_done: bool = False
        self._bars_held: int = 0
        self._breakeven_done: bool = False

    def update(self, position: Position, current_price: float, funding_cost: float = 0.0) -> ExitAction:
        """Called each tick with current price. Returns exit action if any."""
        self._bars_held += 1

        # Track extremes for trailing stop
        if self._highest_price is None or current_price > self._highest_price:
            self._highest_price = current_price
        if self._lowest_price is None or current_price < self._lowest_price:
            self._lowest_price = current_price

        # 1. Hard stop loss
        if self._check_stop_loss(position, current_price):
            logger.info("exit: stop loss hit at %.2f", current_price)
            return ExitAction(close=True, quantity=position.size, reason="stop_loss")

        # 2. Time-based exit
        if self.config.time_exit_bars > 0 and self._bars_held >= self.config.time_exit_bars:
            logger.info("exit: time limit (%d bars)", self._bars_held)
            return ExitAction(close=True, quantity=position.size, reason="time_exit")

        # 3. Funding cost exit
        if self.config.funding_exit_threshold > 0 and abs(funding_cost) > self.config.funding_exit_threshold:
            logger.info("exit: funding cost %.4f > threshold %.4f", funding_cost, self.config.funding_exit_threshold)
            return ExitAction(close=True, quantity=position.size, reason="funding_cost")

        # 4. Breakeven — move SL to entry after profit > breakeven_atr
        if not self._breakeven_done and self.config.breakeven_atr > 0:
            profit_distance = self._profit_distance(position, current_price)
            if profit_distance >= self.config.breakeven_atr * self.atr:
                self._breakeven_done = True
                new_sl = position.entry_price
                logger.info("exit manager: breakeven triggered, new SL=%.2f", new_sl)
                return ExitAction(
                    close=False,
                    update_stop_loss=new_sl,
                    reason="breakeven",
                )

        # 5. Partial close at profit target
        if not self._partial_done and self.config.partial_close_atr > 0:
            profit_distance = self._profit_distance(position, current_price)
            if profit_distance >= self.config.partial_close_atr * self.atr:
                self._partial_done = True
                close_qty = position.size * self.config.partial_close_pct
                logger.info("exit: partial close %.2f at %.2f", close_qty, current_price)
                return ExitAction(close=True, quantity=close_qty, reason="partial_take_profit")

        # 6. Trailing stop
        trailing_dist = self.config.trailing_stop_atr * self.atr
        if position.direction == Direction.LONG and self._highest_price is not None:
            trailing_sl = self._highest_price - trailing_dist
            if trailing_sl > position.stop_loss and current_price <= trailing_sl:
                logger.info("exit: trailing stop hit at %.2f (peak=%.2f)", current_price, self._highest_price)
                return ExitAction(close=True, quantity=position.size, reason="trailing_stop")
        elif position.direction == Direction.SHORT and self._lowest_price is not None:
            trailing_sl = self._lowest_price + trailing_dist
            if trailing_sl < position.stop_loss and current_price >= trailing_sl:
                logger.info("exit: trailing stop hit at %.2f (low=%.2f)", current_price, self._lowest_price)
                return ExitAction(close=True, quantity=position.size, reason="trailing_stop")

        return ExitAction(close=False, reason="hold")

    def _check_stop_loss(self, position: Position, price: float) -> bool:
        if position.direction == Direction.LONG:
            return price <= position.stop_loss
        return price >= position.stop_loss

    def _profit_distance(self, position: Position, price: float) -> float:
        if position.direction == Direction.LONG:
            return price - position.entry_price
        return position.entry_price - price

    def build_close_order(self, position: Position, quantity: Optional[float] = None) -> Order:
        close_qty = quantity if quantity is not None else position.size
        return Order(
            symbol=position.symbol,
            side=OrderSide.SELL if position.direction == Direction.LONG else OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=close_qty,
            reduce_only=True,
        )


@dataclass
class ExitAction:
    close: bool
    quantity: float = 0.0
    update_stop_loss: Optional[float] = None
    reason: str = ""
