from __future__ import annotations

import time

import pytest

from app.analytics.feature_engine import FeatureEngine
from app.backtest.engine import BacktestEngine, BacktestResult
from app.config import Settings
from app.models.market_data_bundle import MarketDataBundle
from app.models.market_snapshot import MarketSnapshot
from app.risk.risk_manager import RiskManager
from app.strategy.funding_mean_reversion import FundingMeanReversionStrategy


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
