from __future__ import annotations

from collections.abc import Sequence
from statistics import mean, pstdev
from typing import Any

from app.models.feature_vector import FeatureVector
from app.models.market_snapshot import MarketSnapshot
from app.models.onchain_snapshot import OnChainSnapshot
from app.models.news_impact import NewsImpactReport
from app.ports.analytics_port import AnalyticsPort


class FeatureEngine(AnalyticsPort):
    """Builds normalized features from market and auxiliary inputs.

    The current implementation is intentionally deterministic and lightweight.
    It is designed as the first production-safe layer that can later be extended
    with richer derivatives, on-chain, and event inputs without changing the
    FeatureVector contract.
    """

    def build_features(self, market_data: Any) -> FeatureVector:
        bundle = self._normalize_bundle(market_data)

        market: MarketSnapshot = bundle["market"]
        price_history: list[float] = bundle["price_history"]
        volume_history: list[float] = bundle["volume_history"]
        oi_history: list[float] = bundle["oi_history"]
        funding_history: list[float] = bundle["funding_history"]
        liquidation_above: float = bundle["liquidation_above"]
        liquidation_below: float = bundle["liquidation_below"]
        onchain: OnChainSnapshot | None = bundle["onchain"]
        news: NewsImpactReport | None = bundle["news"]

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
        news_score = self._compute_news_score(news)
        onchain_score = self._compute_onchain_score(onchain)
        regime_label = self._classify_regime(price_history, atr, volume_ratio)

        return FeatureVector(
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
            liquidation_above=liquidation_above,
            liquidation_below=liquidation_below,
            news_score=news_score,
            onchain_score=onchain_score,
            regime_label=regime_label,
        )

    def _normalize_bundle(self, market_data: Any) -> dict[str, Any]:
        if isinstance(market_data, MarketSnapshot):
            return {
                "market": market_data,
                "price_history": [market_data.price],
                "volume_history": [market_data.volume],
                "oi_history": [],
                "funding_history": [],
                "liquidation_above": 0.0,
                "liquidation_below": 0.0,
                "onchain": None,
                "news": None,
            }

        if isinstance(market_data, dict):
            market = market_data.get("market")
            if not isinstance(market, MarketSnapshot):
                raise TypeError("market_data['market'] must be a MarketSnapshot")

            return {
                "market": market,
                "price_history": list(market_data.get("price_history", [market.price])),
                "volume_history": list(market_data.get("volume_history", [market.volume])),
                "oi_history": list(market_data.get("oi_history", [])),
                "funding_history": list(market_data.get("funding_history", [])),
                "liquidation_above": float(market_data.get("liquidation_above", 0.0)),
                "liquidation_below": float(market_data.get("liquidation_below", 0.0)),
                "onchain": market_data.get("onchain"),
                "news": market_data.get("news"),
            }

        raise TypeError("market_data must be MarketSnapshot or dict bundle")

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
        if news.bias.upper() in {"BULLISH", "BOOST_LONG"}:
            signed = 1.0
        elif news.bias.upper() in {"BEARISH", "BOOST_SHORT"}:
            signed = -1.0
        elif news.block_long and not news.block_short:
            signed = -1.0
        elif news.block_short and not news.block_long:
            signed = 1.0
        return signed * news.severity * news.confidence

    def _compute_onchain_score(self, onchain: OnChainSnapshot | None) -> float:
        if onchain is None:
            return 0.0
        flow_component = onchain.exchange_outflow - onchain.exchange_inflow
        whale_component = onchain.whale_activity
        mvrv_component = -onchain.mvrv
        return flow_component + whale_component + mvrv_component

    def _classify_regime(self, prices: Sequence[float], atr: float, volume_ratio: float) -> str:
        if len(prices) < 2:
            return "UNKNOWN"
        trend = prices[-1] - prices[0]
        if atr == 0 and volume_ratio < 1.0:
            return "RANGE"
        if abs(trend) <= atr:
            return "RANGE"
        if trend > 0 and volume_ratio >= 1.0:
            return "TREND_UP"
        if trend < 0 and volume_ratio >= 1.0:
            return "TREND_DOWN"
        return "VOLATILE"
