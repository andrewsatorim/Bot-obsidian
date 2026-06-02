"""Multi-timeframe collection, context cache and weighted scoring — no network.

Everything is mocked: a fake OHLCV feed (counts calls per timeframe), a fake
Coinglass provider, a deterministic feature engine (regime from the close trend),
and a stub strategy. No sleeping — the context cache uses an injectable clock.
"""

from __future__ import annotations

import asyncio
import math

import pytest

import app.signal_engine.setups as setups_mod
from app.models.enums import Direction, RegimeLabel
from app.models.feature_vector import FeatureVector
from app.models.market_data_bundle import MarketDataBundle
from app.models.signal import Signal
from app.ports.strategy_port import StrategyPort
from app.signal_engine.config import SignalSettings
from app.signal_engine.context import ContextCache, ContextDirection, combine_context
from app.signal_engine.market_data import FactorAvailability, SymbolFeed
from app.signal_engine.multi_tf import (
    MultiTimeframeCollector,
    bundle_from_ohlcv,
)
from app.signal_engine.setups import (
    compute_quality,
    context_alignment_score,
    entry_momentum_aligned,
    regime_aligns,
    select_setups,
)


# --------------------------------------------------------------------------- #
# Fakes / helpers
# --------------------------------------------------------------------------- #
def _ohlcv(closes: list[float]) -> list[list[float]]:
    """Raw ccxt rows [ts, o, h, l, c, v] from a list of closes."""
    return [[(i + 1) * 60_000, c, c, c, c, 100.0] for i, c in enumerate(closes)]


RISING = _ohlcv([100, 101, 102, 103, 104, 105])
FALLING = _ohlcv([105, 104, 103, 102, 101, 100])
FLAT = _ohlcv([100, 100, 100, 100, 100, 100])


class FakeOHLCVFeed:
    """Returns canned OHLCV per timeframe and records every (symbol, tf) call."""

    def __init__(self, per_tf: dict[str, list[list[float]]]) -> None:
        self.per_tf = per_tf
        self.calls: list[tuple[str, str]] = []

    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> list[list[float]]:
        self.calls.append((symbol, timeframe))
        return self.per_tf.get(timeframe, FLAT)


class FakeProvider:
    """Stand-in for the Coinglass/ccxt provider: supplies liquidity/OI + availability."""

    def __init__(
        self,
        availability: FactorAvailability,
        liq_above: float = 0.0,
        liq_below: float = 0.0,
        oi_history: list[float] | None = None,
    ) -> None:
        self.availability = availability
        self.liq_above = liq_above
        self.liq_below = liq_below
        self.oi_history = oi_history or []
        self.calls: list[str] = []

    async def fetch(self, symbol: str) -> SymbolFeed:
        self.calls.append(symbol)
        bundle = bundle_from_ohlcv(symbol, FLAT).model_copy(
            update={
                "liquidation_above": self.liq_above,
                "liquidation_below": self.liq_below,
                "oi_history": self.oi_history,
            }
        )
        return SymbolFeed(bundle, self.availability)


def _fv(regime: RegimeLabel, *, price: float, oi_history: list[float], liq_a: float, liq_b: float) -> FeatureVector:
    oi_delta = (oi_history[-1] - oi_history[-2]) if len(oi_history) >= 2 else 0.0
    oi_trend = ((oi_history[-1] - oi_history[0]) / abs(oi_history[0])) if len(oi_history) >= 2 and oi_history[0] else 0.0
    return FeatureVector(
        price=price,
        atr=2.0,
        volatility_regime=0.01,
        volume_ratio=1.2,
        volume_spike=False,
        oi_delta=oi_delta,
        oi_trend=oi_trend,
        funding=0.0,
        funding_zscore=0.0,
        spread=0.1,
        slippage_estimate=0.1,
        liquidation_above=liq_a,
        liquidation_below=liq_b,
        news_score=0.0,
        onchain_score=0.0,
        regime_label=regime,
    )


class FakeFeatureEngine:
    """Deterministic: regime from the close trend; carries liq/OI from the bundle."""

    def build_features(self, bundle: MarketDataBundle) -> FeatureVector:
        ph = bundle.price_history
        if ph[-1] > ph[0]:
            regime = RegimeLabel.TREND_UP
        elif ph[-1] < ph[0]:
            regime = RegimeLabel.TREND_DOWN
        else:
            regime = RegimeLabel.RANGE
        return _fv(
            regime,
            price=ph[-1],
            oi_history=bundle.oi_history,
            liq_a=bundle.liquidation_above,
            liq_b=bundle.liquidation_below,
        )


class StubStrategy(StrategyPort):
    def __init__(self, signal: Signal | None) -> None:
        self._signal = signal

    def generate_signal(self, features: FeatureVector) -> Signal | None:
        return self._signal


def _signal(direction: Direction, strength: float = 0.9) -> Signal:
    return Signal(symbol="X", direction=direction, strength=strength, timestamp=1)


# --------------------------------------------------------------------------- #
# bundle_from_ohlcv
# --------------------------------------------------------------------------- #
def test_bundle_from_ohlcv_extracts_closes_and_volumes() -> None:
    b = bundle_from_ohlcv("BTC/USDT:USDT", RISING)
    assert b.price_history == [100, 101, 102, 103, 104, 105]
    assert b.volume_history == [100.0] * 6
    assert b.market.price == 105  # last close


# --------------------------------------------------------------------------- #
# MultiTimeframeCollector
# --------------------------------------------------------------------------- #
def test_collector_fetches_eval_setup_entry_and_uses_provider() -> None:
    settings = SignalSettings()  # eval 15m/30m/1h/4h, setup 15m, entry 5m
    feed = FakeOHLCVFeed({})
    provider = FakeProvider(FactorAvailability(liquidity=True, oi=True), liq_above=9_000, oi_history=[10, 11])
    collector = MultiTimeframeCollector(feed, provider, settings)

    mtf = asyncio.run(collector.collect("BTC/USDT:USDT"))

    fetched = {tf for _, tf in feed.calls}
    assert fetched == {"5m", "15m", "30m", "1h", "4h"}  # entry+eval, setup(15m) deduped
    assert "1d" not in fetched and "12h" not in fetched  # context is NOT the collector's job
    assert provider.calls == ["BTC/USDT:USDT"]  # Coinglass fetched once
    # Coinglass data folded into the setup bundle.
    assert mtf.setup.liquidation_above == 9_000
    assert mtf.setup.oi_history == [10, 11]
    assert set(mtf.evals.keys()) == {"15m", "30m", "1h", "4h"}
    assert mtf.availability.liquidity is True


# --------------------------------------------------------------------------- #
# ContextCache — daily priority + caching
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "daily,h12,expected",
    [
        (RegimeLabel.TREND_UP, RegimeLabel.TREND_UP, ContextDirection.BULLISH),
        (RegimeLabel.TREND_UP, RegimeLabel.RANGE, ContextDirection.BULLISH),    # 12h doesn't flip
        (RegimeLabel.TREND_UP, RegimeLabel.TREND_DOWN, ContextDirection.NEUTRAL),  # dampened, not bear
        (RegimeLabel.TREND_DOWN, RegimeLabel.TREND_DOWN, ContextDirection.BEARISH),
        (RegimeLabel.TREND_DOWN, RegimeLabel.TREND_UP, ContextDirection.NEUTRAL),
        (RegimeLabel.RANGE, RegimeLabel.TREND_UP, ContextDirection.NEUTRAL),    # directionless daily
    ],
)
def test_combine_context_daily_priority(daily, h12, expected) -> None:
    assert combine_context(daily, h12) == expected


def test_context_cache_refreshes_at_most_once_per_window() -> None:
    settings = SignalSettings(context_refresh_sec=1000.0, context_timeframes=["1d", "12h"])
    feed = FakeOHLCVFeed({"1d": RISING, "12h": RISING})
    now = {"t": 0.0}
    cache = ContextCache(feed=feed, settings=settings, feature_engine=FakeFeatureEngine(), clock=lambda: now["t"])

    d1 = asyncio.run(cache.get("BTC"))
    assert d1 == ContextDirection.BULLISH
    assert len(feed.calls) == 2  # 1d + 12h fetched once

    now["t"] = 500.0  # within the window
    asyncio.run(cache.get("BTC"))
    assert len(feed.calls) == 2  # served from cache, no refetch

    now["t"] = 1500.0  # past the window
    asyncio.run(cache.get("BTC"))
    assert len(feed.calls) == 4  # refreshed


# --------------------------------------------------------------------------- #
# Scoring primitives
# --------------------------------------------------------------------------- #
def test_regime_aligns() -> None:
    assert regime_aligns(RegimeLabel.TREND_UP, is_long=True)
    assert not regime_aligns(RegimeLabel.TREND_DOWN, is_long=True)
    assert regime_aligns(RegimeLabel.TREND_DOWN, is_long=False)
    assert not regime_aligns(RegimeLabel.RANGE, is_long=True)


def test_context_alignment_score() -> None:
    assert context_alignment_score(ContextDirection.BULLISH, True, 0.5) == 1.0
    assert context_alignment_score(ContextDirection.BEARISH, True, 0.5) == 0.0
    assert context_alignment_score(ContextDirection.NEUTRAL, True, 0.5) == 0.5


def test_entry_momentum_aligned() -> None:
    assert entry_momentum_aligned(bundle_from_ohlcv("X", RISING), is_long=True)
    assert not entry_momentum_aligned(bundle_from_ohlcv("X", FALLING), is_long=True)
    assert not entry_momentum_aligned(bundle_from_ohlcv("X", FLAT), is_long=True)


def test_compute_quality_weighted_blend_and_tristate_exclusion() -> None:
    # weights: signal1 regime1 eval2 context1.5 entry0.5 (liq/oi excluded when None)
    s = SignalSettings()
    full = {"signal": True, "regime": True, "liquidity": None, "oi": None}
    # all soft components perfect -> 1.0
    assert math.isclose(compute_quality(full, 1.0, 1.0, 1.0, s), 1.0)
    # eval agreement 0.5 -> (1+1+1+1.5+0.5)/6 = 5/6
    assert math.isclose(compute_quality(full, 0.5, 1.0, 1.0, s), 5.0 / 6.0)
    # Coinglass available: liquidity True, oi False -> denom grows to 8
    with_cg = {"signal": True, "regime": True, "liquidity": True, "oi": False}
    # numerator: 1+1+2+1.5+0.5 +1(liq) +0(oi) = 7 ; denom 8
    assert math.isclose(compute_quality(with_cg, 1.0, 1.0, 1.0, s), 7.0 / 8.0)


# --------------------------------------------------------------------------- #
# select_setups end-to-end (collector + context cache + weighted score)
# --------------------------------------------------------------------------- #
def _wire(per_tf: dict[str, list[list[float]]], signal: Signal | None, monkeypatch):
    settings = SignalSettings(
        symbols=["BTC/USDT:USDT"],
        min_confidence=0.4,
        min_quality=0.5,
        context_refresh_sec=1000.0,
    )
    feed = FakeOHLCVFeed(per_tf)
    provider = FakeProvider(FactorAvailability(liquidity=False, oi=False))  # Coinglass off -> tri-state
    fe = FakeFeatureEngine()
    collector = MultiTimeframeCollector(feed, provider, settings)
    cache = ContextCache(feed=feed, settings=settings, feature_engine=fe, clock=lambda: 0.0)
    monkeypatch.setitem(setups_mod.STRATEGY_FACTORIES, "TrendFollowing", lambda sym: StubStrategy(signal))
    return settings, collector, cache, fe


def test_select_setups_full_agreement_high_quality(monkeypatch) -> None:
    per_tf = {tf: RISING for tf in ("5m", "15m", "30m", "1h", "4h", "1d", "12h")}
    settings, collector, cache, fe = _wire(per_tf, _signal(Direction.LONG), monkeypatch)

    setups = asyncio.run(select_setups(settings.symbols, collector, cache, settings, fe))

    assert len(setups) == 1
    s = setups[0]
    assert s.direction == "LONG"
    assert s.eval_agreement == 1.0           # all eval TFs rising
    assert s.context == "BULLISH"            # daily+12h up
    assert s.entry_aligned is True
    assert math.isclose(s.quality, 1.0)      # every soft component perfect, Coinglass excluded


def test_select_setups_dropped_when_timeframes_disagree(monkeypatch) -> None:
    # setup/15m rising (regime ok + one eval vote), the rest falling, context bearish.
    per_tf = {"15m": RISING, "30m": FALLING, "1h": FALLING, "4h": FALLING,
              "5m": FALLING, "1d": FALLING, "12h": FALLING}
    settings, collector, cache, fe = _wire(per_tf, _signal(Direction.LONG), monkeypatch)

    setups = asyncio.run(select_setups(settings.symbols, collector, cache, settings, fe))

    # quality = (signal1 + regime1 + eval(2*0.25) + context0 + entry0)/6 = 2.5/6 ≈ 0.417 < 0.5
    assert setups == []


def test_select_setups_skips_when_no_signal(monkeypatch) -> None:
    per_tf = {tf: RISING for tf in ("5m", "15m", "30m", "1h", "4h", "1d", "12h")}
    settings, collector, cache, fe = _wire(per_tf, None, monkeypatch)

    assert asyncio.run(select_setups(settings.symbols, collector, cache, settings, fe)) == []
