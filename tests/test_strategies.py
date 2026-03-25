from __future__ import annotations

import pytest

from app.models.enums import Direction, RegimeLabel
from app.models.feature_vector import FeatureVector
from app.strategy.breakout import BreakoutStrategy
from app.strategy.fusion import StrategyFusion
from app.strategy.trend_following import TrendFollowingStrategy


def _features(**overrides) -> FeatureVector:
    defaults = dict(
        price=65000.0, atr=500.0, volatility_regime=0.02,
        volume_ratio=1.2, volume_spike=False,
        oi_delta=100.0, oi_trend=0.05,
        funding=0.001, funding_zscore=0.5,
        spread=20.0, slippage_estimate=21.0,
        liquidation_above=70000.0, liquidation_below=60000.0,
        news_score=0.0, onchain_score=0.0,
        regime_label=RegimeLabel.RANGE,
    )
    defaults.update(overrides)
    return FeatureVector(**defaults)


class TestBreakoutStrategy:
    def test_no_signal_in_range(self):
        s = BreakoutStrategy(symbol="BTC")
        assert s.generate_signal(_features(regime_label=RegimeLabel.RANGE)) is None

    def test_long_signal_trend_up_with_volume(self):
        s = BreakoutStrategy(symbol="BTC")
        f = _features(regime_label=RegimeLabel.TREND_UP, volume_spike=True, oi_trend=0.05)
        sig = s.generate_signal(f)
        assert sig is not None
        assert sig.direction == Direction.LONG

    def test_short_signal_trend_down(self):
        s = BreakoutStrategy(symbol="BTC")
        f = _features(regime_label=RegimeLabel.TREND_DOWN, volume_ratio=2.0, oi_trend=0.05)
        sig = s.generate_signal(f)
        assert sig is not None
        assert sig.direction == Direction.SHORT

    def test_rejected_low_oi(self):
        s = BreakoutStrategy(symbol="BTC")
        f = _features(regime_label=RegimeLabel.TREND_UP, volume_spike=True, oi_trend=0.01)
        assert s.generate_signal(f) is None


class TestTrendFollowing:
    def test_no_signal_in_range(self):
        s = TrendFollowingStrategy(symbol="BTC")
        assert s.generate_signal(_features(regime_label=RegimeLabel.RANGE)) is None

    def test_long_in_trend_up(self):
        s = TrendFollowingStrategy(symbol="BTC")
        f = _features(regime_label=RegimeLabel.TREND_UP, oi_trend=0.05)
        sig = s.generate_signal(f)
        assert sig is not None
        assert sig.direction == Direction.LONG

    def test_reject_high_volatility(self):
        s = TrendFollowingStrategy(symbol="BTC", max_volatility=0.03)
        f = _features(regime_label=RegimeLabel.TREND_UP, volatility_regime=0.05)
        assert s.generate_signal(f) is None


class TestFusion:
    def test_no_signal_when_no_agreement(self):
        from app.strategy.funding_mean_reversion import FundingMeanReversionStrategy
        fusion = StrategyFusion(
            strategies=[(FundingMeanReversionStrategy("BTC"), 1.0)],
            min_agreement=2,
        )
        f = _features(funding_zscore=3.0)
        # Only 1 strategy can fire, but min_agreement=2
        assert fusion.generate_signal(f) is None

    def test_signal_when_single_agreement_ok(self):
        from app.strategy.funding_mean_reversion import FundingMeanReversionStrategy
        fusion = StrategyFusion(
            strategies=[(FundingMeanReversionStrategy("BTC"), 1.0)],
            min_agreement=1,
        )
        f = _features(funding_zscore=3.0)
        sig = fusion.generate_signal(f)
        assert sig is not None
        assert sig.direction == Direction.SHORT

    def test_weighted_strength(self):
        from app.strategy.funding_mean_reversion import FundingMeanReversionStrategy
        s1 = FundingMeanReversionStrategy("BTC")
        s2 = FundingMeanReversionStrategy("BTC")
        fusion = StrategyFusion(strategies=[(s1, 1.0), (s2, 1.0)], min_agreement=1)
        f = _features(funding_zscore=3.0)
        sig = fusion.generate_signal(f)
        assert sig is not None
        assert 0 < sig.strength <= 1.0
