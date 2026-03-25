from __future__ import annotations

import pytest

from app.analytics.feature_engine import FeatureEngine
from app.models.enums import NewsBias, RegimeLabel
from app.models.market_data_bundle import MarketDataBundle
from app.models.market_snapshot import MarketSnapshot
from app.models.news_impact import NewsImpactReport
from app.models.onchain_snapshot import OnChainSnapshot


@pytest.fixture
def engine():
    return FeatureEngine()


class TestFeatureEngine:
    def test_build_features_minimal(self, engine, market_data_bundle):
        fv = engine.build_features(market_data_bundle)
        assert fv.price > 0
        assert isinstance(fv.regime_label, RegimeLabel)

    def test_atr_proxy_single_price(self, engine):
        assert engine._compute_atr_proxy([100.0]) == 0.0

    def test_atr_proxy_multiple_prices(self, engine):
        result = engine._compute_atr_proxy([100.0, 105.0, 102.0])
        assert result > 0

    def test_volatility_regime_constant_prices(self, engine):
        result = engine._compute_volatility_regime([100.0, 100.0, 100.0])
        assert result == 0.0

    def test_volume_ratio_zero_baseline(self, engine):
        result = engine._compute_volume_ratio(100.0, [])
        assert result == 0.0

    def test_zscore_single_value(self, engine):
        result = engine._compute_zscore([1.0])
        assert result == 0.0

    def test_zscore_normal(self, engine):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = engine._compute_zscore(values)
        assert abs(result) > 0

    def test_onchain_score_none(self, engine):
        assert engine._compute_onchain_score(None) == 0.0

    def test_onchain_score_normalized(self, engine):
        onchain = OnChainSnapshot(
            symbol="BTC", exchange_inflow=1000.0, exchange_outflow=500.0,
            whale_activity=50.0, mvrv=1.5, timestamp=1,
        )
        score = engine._compute_onchain_score(onchain)
        assert -1.0 <= score <= 1.0

    def test_news_score_bullish(self, engine):
        news = NewsImpactReport(
            symbol="BTC", bias=NewsBias.BULLISH,
            severity=0.8, confidence=0.9,
            block_long=False, block_short=False,
        )
        score = engine._compute_news_score(news)
        assert score > 0

    def test_news_score_bearish(self, engine):
        news = NewsImpactReport(
            symbol="BTC", bias=NewsBias.BEARISH,
            severity=0.8, confidence=0.9,
            block_long=False, block_short=False,
        )
        score = engine._compute_news_score(news)
        assert score < 0

    def test_classify_regime_trend_up(self, engine):
        prices = [100.0 + i * 5.0 for i in range(20)]
        result = engine._classify_regime(prices, atr=3.0, volume_ratio=1.5)
        assert result == RegimeLabel.TREND_UP

    def test_classify_regime_range(self, engine):
        prices = [100.0, 100.5, 99.5, 100.0, 100.2]
        result = engine._classify_regime(prices, atr=5.0, volume_ratio=0.8)
        assert result == RegimeLabel.RANGE

    def test_classify_regime_unknown_single(self, engine):
        result = engine._classify_regime([100.0], atr=0.0, volume_ratio=0.0)
        assert result == RegimeLabel.UNKNOWN
