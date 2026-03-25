from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from app.models.enums import Direction, OrderSide, OrderStatus, OrderType
from app.models.execution_report import ExecutionReport
from app.models.feature_vector import FeatureVector
from app.models.market_data_bundle import MarketDataBundle
from app.models.order import Order
from app.models.signal import Signal
from app.models.trade_candidate import TradeCandidate
from app.ports.analytics_port import AnalyticsPort
from app.ports.data_feed_port import DataFeedPort
from app.ports.risk_port import RiskPort
from app.ports.strategy_port import StrategyPort

logger = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    entry_price: float
    exit_price: float
    direction: Direction
    quantity: float
    pnl: float
    fee: float
    entry_idx: int
    exit_idx: int


@dataclass
class BacktestResult:
    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    initial_equity: float = 10_000.0

    @property
    def final_equity(self) -> float:
        return self.equity_curve[-1] if self.equity_curve else self.initial_equity

    @property
    def total_return_pct(self) -> float:
        return (self.final_equity - self.initial_equity) / self.initial_equity * 100

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def winning_trades(self) -> int:
        return sum(1 for t in self.trades if t.pnl > 0)

    @property
    def losing_trades(self) -> int:
        return sum(1 for t in self.trades if t.pnl <= 0)

    @property
    def win_rate(self) -> float:
        return self.winning_trades / self.total_trades if self.total_trades else 0.0

    @property
    def profit_factor(self) -> float:
        gross_profit = sum(t.pnl for t in self.trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in self.trades if t.pnl < 0))
        return gross_profit / gross_loss if gross_loss > 0 else float("inf")

    @property
    def max_drawdown_pct(self) -> float:
        if not self.equity_curve:
            return 0.0
        peak = self.equity_curve[0]
        max_dd = 0.0
        for eq in self.equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100
            if dd > max_dd:
                max_dd = dd
        return max_dd

    @property
    def sharpe_ratio(self) -> float:
        if len(self.equity_curve) < 2:
            return 0.0
        returns = []
        for i in range(1, len(self.equity_curve)):
            r = (self.equity_curve[i] - self.equity_curve[i - 1]) / self.equity_curve[i - 1]
            returns.append(r)
        if not returns:
            return 0.0
        import statistics
        mean_r = statistics.mean(returns)
        std_r = statistics.pstdev(returns)
        if std_r == 0:
            return 0.0
        # Annualize assuming daily returns, 365 trading days for crypto
        return (mean_r / std_r) * (365 ** 0.5)

    @property
    def sortino_ratio(self) -> float:
        if len(self.equity_curve) < 2:
            return 0.0
        returns = []
        for i in range(1, len(self.equity_curve)):
            r = (self.equity_curve[i] - self.equity_curve[i - 1]) / self.equity_curve[i - 1]
            returns.append(r)
        if not returns:
            return 0.0
        import statistics
        mean_r = statistics.mean(returns)
        downside = [r for r in returns if r < 0]
        if not downside:
            return float("inf")
        downside_std = statistics.pstdev(downside)
        if downside_std == 0:
            return 0.0
        return (mean_r / downside_std) * (365 ** 0.5)

    @property
    def calmar_ratio(self) -> float:
        if self.max_drawdown_pct == 0:
            return float("inf")
        return self.total_return_pct / self.max_drawdown_pct

    @property
    def avg_trade_pnl(self) -> float:
        return sum(t.pnl for t in self.trades) / self.total_trades if self.total_trades else 0.0

    @property
    def expectancy(self) -> float:
        if not self.total_trades:
            return 0.0
        avg_win = (
            sum(t.pnl for t in self.trades if t.pnl > 0) / self.winning_trades
            if self.winning_trades else 0.0
        )
        avg_loss = (
            abs(sum(t.pnl for t in self.trades if t.pnl < 0)) / self.losing_trades
            if self.losing_trades else 0.0
        )
        return self.win_rate * avg_win - (1 - self.win_rate) * avg_loss

    def summary(self) -> str:
        lines = [
            "═══ Backtest Results ═══",
            f"Total trades:     {self.total_trades}",
            f"Win rate:         {self.win_rate:.1%}",
            f"Profit factor:    {self.profit_factor:.2f}",
            f"Total return:     {self.total_return_pct:.2f}%",
            f"Max drawdown:     {self.max_drawdown_pct:.2f}%",
            f"Sharpe ratio:     {self.sharpe_ratio:.2f}",
            f"Sortino ratio:    {self.sortino_ratio:.2f}",
            f"Calmar ratio:     {self.calmar_ratio:.2f}",
            f"Expectancy:       {self.expectancy:.2f}",
            f"Avg trade PnL:    {self.avg_trade_pnl:.2f}",
            f"Final equity:     {self.final_equity:.2f}",
        ]
        return "\n".join(lines)


FEE_RATE = 0.001  # 0.1%


class BacktestEngine:
    """Runs a strategy over historical MarketDataBundles and produces metrics."""

    def __init__(
        self,
        analytics: AnalyticsPort,
        strategy: StrategyPort,
        risk: RiskPort,
        initial_equity: float = 10_000.0,
        atr_risk_multiplier: float = 1.5,
        max_position_pct: float = 0.02,
        take_profit_pct: float = 0.15,  # 15% PnL on position
        breakeven_after_tp: bool = True,  # Move SL to entry after TP1
    ) -> None:
        self.analytics = analytics
        self.strategy = strategy
        self.risk = risk
        self.initial_equity = initial_equity
        self.atr_multiplier = atr_risk_multiplier
        self.max_position_pct = max_position_pct
        self.take_profit_pct = take_profit_pct
        self.breakeven_after_tp = breakeven_after_tp

    def run(self, data: list[MarketDataBundle]) -> BacktestResult:
        result = BacktestResult(initial_equity=self.initial_equity)
        equity = self.initial_equity
        result.equity_curve.append(equity)

        position: Optional[_OpenPosition] = None

        for idx, bundle in enumerate(data):
            price = bundle.market.price

            # Check exit for open position
            if position is not None:
                closed, pnl, fee = self._check_exit(position, price)
                if closed:
                    result.trades.append(BacktestTrade(
                        entry_price=position.entry_price,
                        exit_price=price,
                        direction=position.direction,
                        quantity=position.quantity,
                        pnl=pnl,
                        fee=fee,
                        entry_idx=position.entry_idx,
                        exit_idx=idx,
                    ))
                    equity += pnl - fee
                    position = None

            # Generate signal if no position
            if position is None:
                features = self.analytics.build_features(bundle)
                signal = self.strategy.generate_signal(features)

                if signal is not None:
                    trade = self._signal_to_trade(signal, features)
                    decision = self.risk.evaluate(trade)

                    if decision.allow_trade:
                        qty = self._compute_size(equity, features.atr, decision.risk_multiplier)
                        entry_fee = price * qty * FEE_RATE
                        position = _OpenPosition(
                            direction=signal.direction,
                            entry_price=price,
                            quantity=qty,
                            stop_loss=trade.stop_loss,
                            take_profit=trade.take_profit or 0.0,
                            entry_idx=idx,
                        )
                        equity -= entry_fee

            result.equity_curve.append(equity)

        # Force close open position at end
        if position is not None:
            price = data[-1].market.price
            _, pnl, fee = self._check_exit(position, price, force=True)
            result.trades.append(BacktestTrade(
                entry_price=position.entry_price,
                exit_price=price,
                direction=position.direction,
                quantity=position.quantity,
                pnl=pnl,
                fee=fee,
                entry_idx=position.entry_idx,
                exit_idx=len(data) - 1,
            ))
            equity += pnl - fee
            result.equity_curve[-1] = equity

        logger.info("backtest complete: %d trades, return=%.2f%%", result.total_trades, result.total_return_pct)
        return result

    def _check_exit(self, pos: _OpenPosition, price: float, force: bool = False) -> tuple[bool, float, float]:
        # Calculate current PnL
        if pos.direction == Direction.LONG:
            pnl = (price - pos.entry_price) * pos.quantity
        else:
            pnl = (pos.entry_price - price) * pos.quantity

        notional = pos.entry_price * pos.quantity
        pnl_pct = pnl / notional if notional > 0 else 0.0

        # Check TP1: +15% PnL on position -> move SL to entry (breakeven)
        if not pos.tp1_hit and pnl_pct >= self.take_profit_pct:
            pos.tp1_hit = True
            if self.breakeven_after_tp:
                pos.stop_loss = pos.entry_price  # Breakeven
                logger.debug("TP1 hit (%.1f%%), SL moved to entry %.2f", pnl_pct * 100, pos.entry_price)

        # Check stop loss
        hit_sl = (
            (pos.direction == Direction.LONG and price <= pos.stop_loss)
            or (pos.direction == Direction.SHORT and price >= pos.stop_loss)
        )

        if hit_sl or force:
            fee = price * pos.quantity * FEE_RATE
            return True, pnl, fee
        return False, 0.0, 0.0

    def _signal_to_trade(self, signal: Signal, features: FeatureVector) -> TradeCandidate:
        from app.models.enums import SetupType
        atr = features.atr if features.atr > 0 else features.price * 0.01
        stop_dist = atr * self.atr_multiplier
        if signal.direction == Direction.LONG:
            sl = features.price - stop_dist
        else:
            sl = features.price + stop_dist
        return TradeCandidate(
            symbol=signal.symbol,
            direction=signal.direction,
            setup_type=SetupType.FUNDING_MEAN_REVERSION,
            entry_price=features.price,
            stop_loss=max(sl, 0.01),
            score=signal.strength,
            expected_value=2.0,
            confidence=signal.strength,
        )

    def _compute_size(self, equity: float, atr: float, risk_mult: float) -> float:
        risk_amount = equity * self.max_position_pct * risk_mult
        stop_dist = atr * self.atr_multiplier
        if stop_dist <= 0:
            return 0.001
        return max(risk_amount / stop_dist, 0.001)


@dataclass
class _OpenPosition:
    direction: Direction
    entry_price: float
    quantity: float
    stop_loss: float
    take_profit: float
    entry_idx: int
    tp1_hit: bool = False
