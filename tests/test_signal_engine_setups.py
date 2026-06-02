"""Unit tests for signal-engine factor scoring — no network, data is built inline.

The four-factor scoring (``score_factors``) is unchanged by the multi-timeframe
work and is tested here. The weighted quality blend, the timeframe consensus and
``select_setups`` orchestration are covered in ``test_signal_engine_multi_tf.py``.
"""

from __future__ import annotations

import time

from app.models.enums import Direction, RegimeLabel
from app.models.feature_vector import FeatureVector
from app.models.signal import Signal
from app.signal_engine.config import SignalSettings
from app.signal_engine.market_data import FactorAvailability
from app.signal_engine.setups import score_factors


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
    """A clean LONG: strong signal, TREND_UP, liquidity above, OI building."""
    settings = SignalSettings(min_confidence=0.4, min_oi_imbalance=0.0)
    features = _features(
        regime=RegimeLabel.TREND_UP, liq_above=5_000, liq_below=1_000, oi_delta=10, oi_trend=0.03
    )
    factors = score_factors(features, _signal(Direction.LONG, 0.8), settings)
    assert factors == {"signal": True, "regime": True, "liquidity": True, "oi": True}


def test_factors_partial_short() -> None:
    """SHORT with weak signal + liquidity on the wrong side -> only 2/4 match."""
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


def test_range_regime_and_flat_oi_fail_factors() -> None:
    settings = SignalSettings(min_confidence=0.4, min_oi_imbalance=0.0)
    features = _features(
        regime=RegimeLabel.RANGE, liq_above=1_000, liq_below=5_000, oi_delta=-5, oi_trend=-0.01
    )
    factors = score_factors(features, _signal(Direction.LONG, 0.9), settings)
    assert factors["regime"] is False
    assert factors["liquidity"] is False  # liquidity below, not above, for a LONG
    assert factors["oi"] is False  # OI shrinking


def test_unavailable_data_marks_factors_none_not_failed() -> None:
    """No liquidity/OI data -> those factors are None ('unavailable'), not False."""
    settings = SignalSettings(min_confidence=0.4)
    features = _features(
        regime=RegimeLabel.TREND_UP, liq_above=0, liq_below=0, oi_delta=0, oi_trend=0
    )
    unavailable = FactorAvailability(liquidity=False, oi=False)
    factors = score_factors(features, _signal(Direction.LONG, 0.8), settings, unavailable)

    assert factors["signal"] is True
    assert factors["regime"] is True
    assert factors["liquidity"] is None  # not False — we simply could not evaluate it
    assert factors["oi"] is None
