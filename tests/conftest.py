from __future__ import annotations

import time

import pytest

from app.config import Settings
from app.models.enums import Direction, NewsBias, OrderStatus, RegimeLabel, SetupType
from app.models.feature_vector import FeatureVector
from app.models.market_data_bundle import MarketDataBundle
from app.models.market_snapshot import MarketSnapshot
from app.models.news_impact import NewsImpactReport
from app.models.onchain_snapshot import OnChainSnapshot
from app.models.signal import Signal
from app.models.trade_candidate import TradeCandidate


@pytest.fixture
def settings():
    return Settings(
        symbol="BTC/USDT",
        paper_trading=True,
        account_equity=10_000.0,
        cooldown_sec=1.0,
        scan_interval_sec=0.1,
    )


@pytest.fixture
def market_snapshot():
    return MarketSnapshot(
        symbol="BTC/USDT",
        price=65000.0,
        volume=1000.0,
        bid=64990.0,
        ask=65010.0,
        timestamp=int(time.time()),
    )


@pytest.fixture
def feature_vector():
    return FeatureVector(
        price=65000.0,
        atr=500.0,
        volatility_regime=0.02,
        volume_ratio=1.2,
        volume_spike=False,
        oi_delta=100.0,
        oi_trend=0.05,
        funding=0.001,
        funding_zscore=0.5,
        spread=20.0,
        slippage_estimate=21.0,
        liquidation_above=70000.0,
        liquidation_below=60000.0,
        news_score=0.0,
        onchain_score=0.0,
        regime_label=RegimeLabel.RANGE,
    )


@pytest.fixture
def signal():
    return Signal(
        symbol="BTC/USDT",
        direction=Direction.LONG,
        strength=0.7,
        timestamp=int(time.time()),
    )


@pytest.fixture
def trade_candidate():
    return TradeCandidate(
        symbol="BTC/USDT",
        direction=Direction.LONG,
        setup_type=SetupType.FUNDING_MEAN_REVERSION,
        entry_price=65000.0,
        stop_loss=64000.0,
        take_profit=67000.0,
        score=0.7,
        expected_value=2.0,
        confidence=0.7,
    )


@pytest.fixture
def market_data_bundle(market_snapshot):
    prices = [64000.0 + i * 50.0 for i in range(20)]
    prices.append(market_snapshot.price)
    return MarketDataBundle(
        market=market_snapshot,
        price_history=prices,
        volume_history=[1000.0] * 20 + [1000.0],
        oi_history=[50000.0 + i * 10 for i in range(21)],
        funding_history=[0.0001 * i for i in range(21)],
    )
