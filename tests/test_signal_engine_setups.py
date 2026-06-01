"""Unit tests for signal-engine setup selection — no network, data is built inline."""

from __future__ import annotations

import time

from app.models.enums import Direction, RegimeLabel
from app.models.feature_vector import FeatureVector
from app.models.market_data_bundle import MarketDataBundle
from app.models.market_snapshot import MarketSnapshot
from app.models.signal import Signal
from app.ports.strategy_port import StrategyPort
from app.signal_engine.config import SignalSettings
from app.signal_engine.setups import (
    quality_from_factors,
    score_factors,
    select_setups,
)


def _features(
    *,
    regime: RegimeLabel,
    liq_above: float,
    liq_below: float,
    oi_delta: float,
    oi_trend: float,
    price: float = 100.0,
    atr: float = 2.0,
) -> FeatureVector:
    return FeatureVector(
        price=price,
        atr=atr,
        volatility_regime=0.01,
        volume_ratio=1.2,
        volume_spike=False,
        oi_delta=oi_delta,
        oi_trend=oi_trend,
        funding=0.0,
        funding_zscore=0.0,
        spread=0.1,
        slippage_estimate=0.1,
        liquidation_above=liq_above,
        liquidation_below=liq_below,
        news_score=0.0,
        onchain_score=0.0,
        regime_label=regime,
    )


def _signal(direction: Direction, strength: float) -> Signal:
    return Signal(symbol="X", direction=direction, strength=strength, timestamp=int(time.time()))


def test_all_four_factors_align_long() -> None:
    """A clean LONG: strong signal, TREND_UP, liquidity above, OI building -> 1.0."""
    settings = SignalSettings(min_confidence=0.4, min_oi_imbalance=0.0)
    features = _features(
        regime=RegimeLabel.TREND_UP, liq_above=5_000, liq_below=1_000, oi_delta=10, oi_trend=0.03
    )
    factors = score_factors(features, _signal(Direction.LONG, 0.8), settings)
    assert factors == {"signal": True, "regime": True, "liquidity": True, "oi": True}
    assert quality_from_factors(factors) == 1.0


def test_factors_partial_short() -> None:
    """SHORT with weak signal + liquidity on the wrong side -> only 2/4 = 0.5."""
    settings = SignalSettings(min_confidence=0.5, min_oi_imbalance=0.0)
    features = _features(
        regime=RegimeLabel.TREND_DOWN,  # regime ok
        liq_above=5_000,  # liquidity above = wrong side for SHORT
        liq_below=1_000,
        oi_delta=10,  # oi building ok
        oi_trend=0.02,
    )
    factors = score_factors(features, _signal(Direction.SHORT, 0.3), settings)  # weak signal
    assert factors == {"signal": False, "regime": True, "liquidity": False, "oi": True}
    assert quality_from_factors(factors) == 0.5


def test_range_regime_and_flat_oi_fail_factors() -> None:
    settings = SignalSettings(min_confidence=0.4, min_oi_imbalance=0.0)
    features = _features(
        regime=RegimeLabel.RANGE, liq_above=1_000, liq_below=5_000, oi_delta=-5, oi_trend=-0.01
    )
    factors = score_factors(features, _signal(Direction.LONG, 0.9), settings)
    assert factors["regime"] is False
    assert factors["liquidity"] is False  # liquidity below, not above, for a LONG
    assert factors["oi"] is False  # OI shrinking
    assert quality_from_factors(factors) == 0.25  # only the signal factor


class _StubStrategy(StrategyPort):
    """Returns a fixed signal regardless of features (deterministic, offline)."""

    def __init__(self, signal: Signal | None) -> None:
        self._signal = signal

    def generate_signal(self, features: FeatureVector) -> Signal | None:
        return self._signal


class _StubFeatureEngine:
    """Returns a pre-baked FeatureVector so no market math/network is involved."""

    def __init__(self, features: FeatureVector) -> None:
        self._features = features

    def build_features(self, market_data: MarketDataBundle) -> FeatureVector:
        return self._features


def _bundle() -> MarketDataBundle:
    return MarketDataBundle(
        market=MarketSnapshot(
            symbol="BTC/USDT:USDT", price=100.0, volume=1.0, bid=99.9, ask=100.1, timestamp=1
        ),
        price_history=[100.0],
        volume_history=[1.0],
    )


def test_select_setups_threshold_filters(monkeypatch) -> None:
    """select_setups keeps high-quality setups and drops sub-threshold ones."""
    import app.signal_engine.setups as setups_mod

    good = _features(
        regime=RegimeLabel.TREND_UP, liq_above=9_000, liq_below=10, oi_delta=20, oi_trend=0.05
    )
    fe = _StubFeatureEngine(good)
    # Force a known strategy that always fires a strong LONG.
    monkeypatch.setitem(
        setups_mod.STRATEGY_FACTORIES,
        "TrendFollowing",
        lambda s: _StubStrategy(_signal(Direction.LONG, 0.9)),
    )

    # quality == 1.0 passes a 0.5 threshold...
    passing = select_setups({"BTC/USDT:USDT": _bundle()}, SignalSettings(min_quality=0.5), fe)
    assert len(passing) == 1
    assert passing[0].direction == "LONG"
    assert passing[0].quality == 1.0

    # ...but a setup missing one factor (quality 0.75) is dropped by a 1.0 floor.
    three_of_four = _features(
        regime=RegimeLabel.TREND_UP, liq_above=10, liq_below=9_000, oi_delta=20, oi_trend=0.05
    )  # liquidity on the wrong side for a LONG -> 3/4 = 0.75
    fe_partial = _StubFeatureEngine(three_of_four)
    none = select_setups({"BTC/USDT:USDT": _bundle()}, SignalSettings(min_quality=1.0), fe_partial)
    assert none == []


def test_select_setups_skips_when_no_signal(monkeypatch) -> None:
    import app.signal_engine.setups as setups_mod

    fe = _StubFeatureEngine(
        _features(regime=RegimeLabel.TREND_UP, liq_above=9_000, liq_below=10, oi_delta=20, oi_trend=0.05)
    )
    monkeypatch.setitem(
        setups_mod.STRATEGY_FACTORIES, "TrendFollowing", lambda s: _StubStrategy(None)
    )
    assert select_setups({"BTC/USDT:USDT": _bundle()}, SignalSettings(), fe) == []
