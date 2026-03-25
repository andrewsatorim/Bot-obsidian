from __future__ import annotations

import pytest

from app.models.enums import Direction, RegimeLabel
from app.models.feature_vector import FeatureVector
from app.strategy.funding_mean_reversion import FundingMeanReversionStrategy


def _make_features(**overrides) -> FeatureVector:
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


@pytest.fixture
def strategy():
    return FundingMeanReversionStrategy(symbol="BTC/USDT")


class TestFundingMeanReversion:
    def test_no_signal_moderate_zscore(self, strategy):
        features = _make_features(funding_zscore=1.0)
        assert strategy.generate_signal(features) is None

    def test_short_signal_high_zscore(self, strategy):
        features = _make_features(funding_zscore=2.5)
        signal = strategy.generate_signal(features)
        assert signal is not None
        assert signal.direction == Direction.SHORT

    def test_long_signal_low_zscore(self, strategy):
        features = _make_features(funding_zscore=-2.5)
        signal = strategy.generate_signal(features)
        assert signal is not None
        assert signal.direction == Direction.LONG

    def test_no_short_in_trend_up(self, strategy):
        features = _make_features(funding_zscore=3.0, regime_label=RegimeLabel.TREND_UP)
        assert strategy.generate_signal(features) is None

    def test_no_long_in_trend_down(self, strategy):
        features = _make_features(funding_zscore=-3.0, regime_label=RegimeLabel.TREND_DOWN)
        assert strategy.generate_signal(features) is None

    def test_reject_high_volatility(self, strategy):
        features = _make_features(funding_zscore=3.0, volatility_regime=0.1)
        assert strategy.generate_signal(features) is None

    def test_reject_opposing_news_long(self, strategy):
        features = _make_features(funding_zscore=-3.0, news_score=-0.8)
        assert strategy.generate_signal(features) is None

    def test_reject_opposing_news_short(self, strategy):
        features = _make_features(funding_zscore=3.0, news_score=0.8)
        assert strategy.generate_signal(features) is None

    def test_signal_strength_scaling(self, strategy):
        features = _make_features(funding_zscore=4.0)
        signal = strategy.generate_signal(features)
        assert signal is not None
        assert signal.strength == 1.0

        features2 = _make_features(funding_zscore=2.5)
        signal2 = strategy.generate_signal(features2)
        assert signal2 is not None
        assert signal2.strength < 1.0
