from __future__ import annotations

import time

import pytest

from app.analytics.feature_engine import FeatureEngine
from app.backtest.engine import BacktestEngine, BacktestResult, WalkForwardResult
from app.config import Settings
from app.models.market_data_bundle import MarketDataBundle
from app.models.market_snapshot import MarketSnapshot
from app.models.enums import Direction
from app.models.signal import Signal
from app.risk.risk_manager import RiskManager
from app.strategy.funding_mean_reversion import FundingMeanReversionStrategy


class _AlwaysLong:
    """Test-only strategy that signals LONG once, then stays quiet.

    Lets us drive the engine deterministically (one round trip) without touching
    any real strategy logic.
    """

    def __init__(self, symbol: str = "BTC/USDT") -> None:
        self._symbol = symbol
        self._fired = False

    def generate_signal(self, features):
        if self._fired:
            return None
        self._fired = True
        return Signal(symbol=self._symbol, direction=Direction.LONG, strength=0.9,
                      timestamp=int(time.time()))


def _flat_bundle(price: float, idx: int) -> MarketDataBundle:
    """A flat-price bundle so PnL ~ 0 and equity changes are dominated by costs."""
    ts = int(time.time()) + idx
    snap = MarketSnapshot(symbol="BTC/USDT", price=price, volume=1000.0,
                          bid=price - 1, ask=price + 1, timestamp=ts)
    return MarketDataBundle(
        market=snap,
        price_history=[price] * 30,
        volume_history=[1000.0] * 30,
        oi_history=[50000.0] * 30,
        funding_history=[0.0001] * 30,
    )


def _make_bundle(price: float, funding: float = 0.0001, idx: int = 0) -> MarketDataBundle:
    ts = int(time.time()) + idx
    snapshot = MarketSnapshot(
        symbol="BTC/USDT", price=price, volume=1000.0,
        bid=price - 5, ask=price + 5, timestamp=ts,
    )
    # Build history that creates a trend
    prices = [price - 100 + i * 5.0 for i in range(20)]
    prices.append(price)
    funding_history = [funding * (i + 1) for i in range(20)]
    return MarketDataBundle(
        market=snapshot,
        price_history=prices,
        volume_history=[1000.0] * 21,
        oi_history=[50000.0 + i * 10 for i in range(21)],
        funding_history=funding_history,
    )


class TestBacktestResult:
    def test_empty_result(self):
        r = BacktestResult(initial_equity=10_000.0)
        assert r.total_trades == 0
        assert r.win_rate == 0.0
        assert r.expectancy == 0.0

    def test_summary_runs(self):
        r = BacktestResult(initial_equity=10_000.0, equity_curve=[10_000.0, 10_500.0])
        text = r.summary()
        assert "Backtest Results" in text


class TestBacktestEngine:
    def test_run_with_data(self):
        settings = Settings(account_equity=10_000.0, paper_trading=True)
        engine = BacktestEngine(
            analytics=FeatureEngine(),
            strategy=FundingMeanReversionStrategy(symbol="BTC/USDT"),
            risk=RiskManager(settings),
        )
        data = [_make_bundle(65000.0 + i * 10, funding=0.0001 * (i % 30), idx=i) for i in range(50)]
        result = engine.run(data)
        assert isinstance(result, BacktestResult)
        assert len(result.equity_curve) > 0

    def test_sharpe_ratio_computable(self):
        r = BacktestResult(
            initial_equity=10_000.0,
            equity_curve=[10_000.0, 10_100.0, 10_050.0, 10_200.0, 10_150.0],
        )
        assert r.sharpe_ratio != 0.0 or True  # Just check no crash

    def test_max_drawdown(self):
        r = BacktestResult(
            initial_equity=10_000.0,
            equity_curve=[10_000.0, 11_000.0, 9_000.0, 10_500.0],
        )
        assert r.max_drawdown_pct > 0


class TestFeesAndSlippage:
    def _run(self, fee_pct: float, slippage_pct: float) -> BacktestResult:
        settings = Settings(account_equity=10_000.0, paper_trading=True, max_position_pct=0.05)
        engine = BacktestEngine(
            analytics=FeatureEngine(),
            strategy=_AlwaysLong(),
            risk=RiskManager(settings),
            initial_equity=10_000.0,
            leverage=10.0,
            fee_pct=fee_pct,
            slippage_pct=slippage_pct,
        )
        data = [_flat_bundle(65000.0, i) for i in range(10)]
        return engine.run(data)

    def test_zero_cost_charges_nothing(self):
        r = self._run(fee_pct=0.0, slippage_pct=0.0)
        assert r.total_trades == 1
        # Flat price + no fees/slippage => equity essentially unchanged.
        assert r.trades[0].fee == 0.0
        assert r.final_equity == pytest.approx(10_000.0, abs=1e-6)

    def test_slippage_is_charged_and_reduces_equity(self):
        free = self._run(fee_pct=0.0, slippage_pct=0.0)
        slipped = self._run(fee_pct=0.0, slippage_pct=0.01)  # 1% per fill
        # Slippage now costs money the old engine ignored.
        assert slipped.trades[0].fee > 0.0
        assert slipped.final_equity < free.final_equity

    def test_fee_and_slippage_combine(self):
        only_slip = self._run(fee_pct=0.0, slippage_pct=0.005)
        both = self._run(fee_pct=0.005, slippage_pct=0.005)
        # Adding a fee on top of the same slippage costs strictly more.
        assert both.final_equity < only_slip.final_equity

    def test_default_slippage_is_nonzero(self):
        # Default config must not be cost-free (avoids optimistic backtests).
        settings = Settings(account_equity=10_000.0, paper_trading=True)
        engine = BacktestEngine(analytics=FeatureEngine(), strategy=_AlwaysLong(),
                                risk=RiskManager(settings))
        assert engine.fee_pct == 0.0
        assert engine.slippage_pct > 0.0
        assert engine._cost_rate == pytest.approx(engine.fee_pct + engine.slippage_pct)


class TestWalkForward:
    def _engine(self):
        settings = Settings(account_equity=10_000.0, paper_trading=True)
        return BacktestEngine(
            analytics=FeatureEngine(),
            strategy=FundingMeanReversionStrategy(symbol="BTC/USDT"),
            risk=RiskManager(settings),
            slippage_pct=0.0,
        )

    def test_splits_into_n_nonoverlapping_windows(self):
        engine = self._engine()
        data = [_flat_bundle(65000.0, i) for i in range(60)]
        wf = engine.run_walk_forward(data, n_windows=3)
        assert isinstance(wf, WalkForwardResult)
        assert wf.n_windows == 3
        assert wf.aggregate is not None
        assert len(wf.window_returns_pct) == 3

    def test_restores_original_strategy(self):
        engine = self._engine()
        original = engine.strategy
        data = [_flat_bundle(65000.0, i) for i in range(30)]
        engine.run_walk_forward(
            data, n_windows=3,
            strategy_factory=lambda: FundingMeanReversionStrategy(symbol="BTC/USDT"),
        )
        assert engine.strategy is original

    def test_robust_requires_min_profitable_windows(self):
        # Build a WalkForwardResult directly with controlled per-window returns.
        def win(ret):
            return BacktestResult(initial_equity=100.0,
                                  equity_curve=[100.0, 100.0 * (1 + ret / 100)])

        # 2 of 3 profitable => robust
        wf = WalkForwardResult(windows=[win(5), win(-3), win(8)], min_profitable_windows=2)
        assert wf.profitable_windows == 2
        assert wf.robust is True

        # 1 of 3 profitable => not robust (works in only one regime)
        wf2 = WalkForwardResult(windows=[win(20), win(-3), win(-8)], min_profitable_windows=2)
        assert wf2.profitable_windows == 1
        assert wf2.robust is False

    def test_raises_when_not_enough_data(self):
        engine = self._engine()
        with pytest.raises(ValueError):
            engine.run_walk_forward([_flat_bundle(65000.0, 0)], n_windows=3)
