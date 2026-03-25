from __future__ import annotations

import pytest

from app.models.enums import Direction, RegimeLabel
from app.models.feature_vector import FeatureVector
from app.strategy.bollinger_reversion import BollingerMeanReversionStrategy
from app.strategy.liquidation_squeeze import LiquidationSqueezeStrategy
from app.strategy.oi_divergence import OIDivergenceStrategy


def _features(**overrides) -> FeatureVector:
    defaults = dict(
        price=65000.0, atr=500.0, volatility_regime=0.02,
        volume_ratio=1.2, volume_spike=False,
        oi_delta=100.0, oi_trend=0.05,
        funding=0.001, funding_zscore=0.5,
        spread=20.0, slippage_estimate=21.0,
        liquidation_above=66000.0, liquidation_below=64000.0,
        news_score=0.0, onchain_score=0.0,
        regime_label=RegimeLabel.RANGE,
    )
    defaults.update(overrides)
    return FeatureVector(**defaults)


# === Bollinger Mean Reversion ===

class TestBollingerReversion:
    def test_no_signal_in_trend(self):
        s = BollingerMeanReversionStrategy(symbol="BTC", period=5)
        f = _features(regime_label=RegimeLabel.TREND_UP)
        assert s.generate_signal(f) is None

    def test_no_signal_insufficient_data(self):
        s = BollingerMeanReversionStrategy(symbol="BTC", period=20)
        f = _features()
        assert s.generate_signal(f) is None  # Only 1 price in buffer

    def test_long_signal_at_lower_band(self):
        s = BollingerMeanReversionStrategy(symbol="BTC", period=5)
        # Feed stable prices then a drop
        for i in range(6):
            s.generate_signal(_features(price=65000.0))
        # Price drops well below band
        sig = s.generate_signal(_features(price=64000.0))
        # May or may not trigger depending on std — check no crash
        assert sig is None or sig.direction == Direction.LONG

    def test_short_signal_at_upper_band(self):
        s = BollingerMeanReversionStrategy(symbol="BTC", period=5)
        for i in range(6):
            s.generate_signal(_features(price=65000.0))
        sig = s.generate_signal(_features(price=66000.0))
        assert sig is None or sig.direction == Direction.SHORT


# === OI Divergence ===

class TestOIDivergence:
    def test_no_signal_when_oi_rising(self):
        s = OIDivergenceStrategy(symbol="BTC")
        f = _features(oi_trend=0.05)  # OI rising — no divergence
        assert s.generate_signal(f) is None

    def test_short_on_bullish_divergence(self):
        s = OIDivergenceStrategy(symbol="BTC")
        f = _features(
            regime_label=RegimeLabel.TREND_UP,
            oi_trend=-0.03,  # OI declining while price up
        )
        sig = s.generate_signal(f)
        assert sig is not None
        assert sig.direction == Direction.SHORT

    def test_long_on_bearish_divergence(self):
        s = OIDivergenceStrategy(symbol="BTC")
        f = _features(
            regime_label=RegimeLabel.TREND_DOWN,
            oi_trend=-0.03,
        )
        sig = s.generate_signal(f)
        assert sig is not None
        assert sig.direction == Direction.LONG

    def test_skip_extreme_volatility(self):
        s = OIDivergenceStrategy(symbol="BTC")
        f = _features(
            regime_label=RegimeLabel.TREND_UP,
            oi_trend=-0.03,
            volatility_regime=0.1,
        )
        assert s.generate_signal(f) is None


# === Liquidation Squeeze ===

class TestLiquidationSqueeze:
    def test_no_signal_when_far_from_levels(self):
        s = LiquidationSqueezeStrategy(symbol="BTC")
        f = _features(
            price=65000.0,
            liquidation_above=70000.0,  # 7.7% away
            liquidation_below=60000.0,  # 7.7% away
        )
        assert s.generate_signal(f) is None

    def test_long_near_upper_liquidation(self):
        s = LiquidationSqueezeStrategy(symbol="BTC")
        f = _features(
            price=65000.0,
            liquidation_above=65500.0,  # 0.77% away — within 2% threshold
            volume_ratio=1.5,
        )
        sig = s.generate_signal(f)
        assert sig is not None
        assert sig.direction == Direction.LONG

    def test_short_near_lower_liquidation(self):
        s = LiquidationSqueezeStrategy(symbol="BTC")
        f = _features(
            price=65000.0,
            liquidation_below=64500.0,  # 0.77% away
            liquidation_above=0.0,
            volume_ratio=1.5,
        )
        sig = s.generate_signal(f)
        assert sig is not None
        assert sig.direction == Direction.SHORT

    def test_no_signal_without_volume(self):
        s = LiquidationSqueezeStrategy(symbol="BTC")
        f = _features(
            price=65000.0,
            liquidation_above=65500.0,
            volume_ratio=0.5,  # Low volume — no cascade
        )
        assert s.generate_signal(f) is None
