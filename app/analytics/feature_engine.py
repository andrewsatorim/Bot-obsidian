from __future__ import annotations

import logging
from collections.abc import Sequence
from statistics import mean, pstdev

from app.models.enums import RegimeLabel
from app.models.feature_vector import FeatureVector
from app.models.market_data_bundle import MarketDataBundle
from app.models.news_impact import NewsImpactReport
from app.models.onchain_snapshot import OnChainSnapshot
from app.ports.analytics_port import AnalyticsPort

logger = logging.getLogger(__name__)


class FeatureEngine(AnalyticsPort):
    """Builds normalized features from market and auxiliary inputs."""

    def build_features(self, market_data: MarketDataBundle) -> FeatureVector:
        market = market_data.market
        price_history = market_data.price_history
        volume_history = market_data.volume_history
        oi_history = market_data.oi_history
        funding_history = market_data.funding_history

        atr = self._compute_atr_proxy(price_history)
        volatility_regime = self._compute_volatility_regime(price_history)
        volume_ratio = self._compute_volume_ratio(market.volume, volume_history)
        volume_spike = volume_ratio >= 1.5
        oi_delta = self._compute_delta(oi_history)
        oi_trend = self._compute_trend_strength(oi_history)
        funding = funding_history[-1] if funding_history else 0.0
        funding_zscore = self._compute_zscore(funding_history)
        spread = max(market.ask - market.bid, 0.0)
        slippage_estimate = self._estimate_slippage(spread, market.volume)
        news_score = self._compute_news_score(market_data.news)
        onchain_score = self._compute_onchain_score(market_data.onchain)
        regime_label = self._classify_regime(price_history, atr, volume_ratio)

        fv = FeatureVector(
            price=market.price,
            atr=atr,
            volatility_regime=volatility_regime,
            volume_ratio=volume_ratio,
            volume_spike=volume_spike,
            oi_delta=oi_delta,
            oi_trend=oi_trend,
            funding=funding,
            funding_zscore=funding_zscore,
            spread=spread,
            slippage_estimate=slippage_estimate,
            liquidation_above=market_data.liquidation_above,
            liquidation_below=market_data.liquidation_below,
            news_score=news_score,
            onchain_score=onchain_score,
            regime_label=regime_label,
        )
        logger.debug("features built: regime=%s atr=%.4f funding_z=%.2f", regime_label, atr, funding_zscore)
        return fv

    # ------------------------------------------------------------------
    # Computation helpers
    # ------------------------------------------------------------------

    def _compute_atr_proxy(self, prices: Sequence[float]) -> float:
        if len(prices) < 2:
            return 0.0
        ranges = [abs(prices[i] - prices[i - 1]) for i in range(1, len(prices))]
        return mean(ranges)

    def _compute_volatility_regime(self, prices: Sequence[float]) -> float:
        if len(prices) < 2:
            return 0.0
        base = mean(prices)
        if base == 0:
            return 0.0
        return pstdev(prices) / base

    def _compute_volume_ratio(self, current_volume: float, volume_history: Sequence[float]) -> float:
        baseline = mean(volume_history) if volume_history else 0.0
        if baseline <= 0:
            return 0.0
        return current_volume / baseline

    def _compute_delta(self, values: Sequence[float]) -> float:
        if len(values) < 2:
            return 0.0
        return values[-1] - values[-2]

    def _compute_trend_strength(self, values: Sequence[float]) -> float:
        if len(values) < 2:
            return 0.0
        start = values[0]
        if start == 0:
            return 0.0
        return (values[-1] - start) / abs(start)

    def _compute_zscore(self, values: Sequence[float]) -> float:
        if len(values) < 2:
            return 0.0
        mu = mean(values)
        sigma = pstdev(values)
        if sigma == 0:
            return 0.0
        return (values[-1] - mu) / sigma

    def _estimate_slippage(self, spread: float, volume: float) -> float:
        if volume <= 0:
            return spread
        return spread * (1.0 + 1.0 / max(volume, 1.0))

    def _compute_news_score(self, news: NewsImpactReport | None) -> float:
        if news is None:
            return 0.0
        signed = 0.0
        bias = news.bias.value
        if bias in {"BULLISH", "BOOST_LONG"}:
            signed = 1.0
        elif bias in {"BEARISH", "BOOST_SHORT"}:
            signed = -1.0
        elif news.block_long and not news.block_short:
            signed = -1.0
        elif news.block_short and not news.block_long:
            signed = 1.0
        return signed * news.severity * news.confidence

    def _compute_onchain_score(self, onchain: OnChainSnapshot | None) -> float:
        if onchain is None:
            return 0.0
        flow = onchain.exchange_outflow - onchain.exchange_inflow
        flow_norm = max(min(flow / max(onchain.exchange_inflow + onchain.exchange_outflow, 1.0), 1.0), -1.0)
        whale_norm = max(min(onchain.whale_activity / 100.0, 1.0), -1.0)
        mvrv_norm = max(min(-onchain.mvrv / 3.0, 1.0), -1.0)
        return (flow_norm + whale_norm + mvrv_norm) / 3.0

    def _classify_regime(self, prices: Sequence[float], atr: float, volume_ratio: float) -> RegimeLabel:
        if len(prices) < 2:
            return RegimeLabel.UNKNOWN
        trend = prices[-1] - prices[0]
        if atr == 0 and volume_ratio < 1.0:
            return RegimeLabel.RANGE
        if abs(trend) <= atr:
            return RegimeLabel.RANGE
        if trend > 0 and volume_ratio >= 1.0:
            return RegimeLabel.TREND_UP
        if trend < 0 and volume_ratio >= 1.0:
            return RegimeLabel.TREND_DOWN
        return RegimeLabel.VOLATILE
