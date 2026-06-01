"""Market-data providers for the signal engine (read-only, never executes).

The engine scores four factors; two of them — the liquidation-heatmap *liquidity*
factor and the *OI imbalance* factor — need data that the plain ccxt feed does not
supply. This module wraps a base ccxt feed and, when a Coinglass key is present,
enriches each bundle with real liquidation + open-interest data.

Crucially, it reports **availability** alongside the data. When Coinglass is
absent or a fetch fails, the affected factors are flagged unavailable so the
scorer marks them "data unavailable" instead of silently counting them as matched
or failed. Nothing here imports an executor, order or port.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from app.models.market_data_bundle import MarketDataBundle

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FactorAvailability:
    """Whether the data backing each data-dependent factor is actually present."""

    liquidity: bool = True
    oi: bool = True


@dataclass(frozen=True)
class SymbolFeed:
    """A symbol's market bundle plus which data-dependent factors are usable."""

    bundle: MarketDataBundle
    availability: FactorAvailability


class BaseFeed(Protocol):
    """Minimal read-only market feed (e.g. CcxtDataFeed)."""

    async def get_market_data(self, symbol: str) -> MarketDataBundle: ...


class CoinglassClient(Protocol):
    """Subset of app.feeds.coinglass_v4.CoinglassV4 the engine relies on."""

    def get_liquidation_heatmap(self, symbol: str = ...) -> dict: ...
    def get_oi_realtime(self, symbol: str = ...) -> dict: ...


class MarketDataProvider(Protocol):
    async def fetch(self, symbol: str) -> SymbolFeed: ...


def _base_asset(symbol: str) -> str:
    """`BTC/USDT:USDT` -> `BTC` (Coinglass keys are bare base assets)."""
    return symbol.split("/")[0].split(":")[0].strip().upper()


def _oi_series_from_realtime(oi: dict) -> list[float]:
    """Turn Coinglass realtime OI into a 2-point history FeatureEngine can use.

    We reconstruct the prior value from the 1h % change so oi_delta/oi_trend come
    out with the right sign and magnitude. Returns [] when OI is missing/zero.
    """
    total = oi.get("total") or {}
    now = float(total.get("oi_qty", 0) or 0)
    if now <= 0:
        return []
    change_1h_pct = float(total.get("change_1h", 0) or 0)
    prev = now / (1.0 + change_1h_pct / 100.0) if change_1h_pct != -100.0 else now
    return [prev, now]


class CcxtOnlyProvider:
    """Fallback provider: ccxt data only.

    The ccxt feed carries no liquidation heatmap and usually <2 OI points, so the
    liquidity and OI factors are reported unavailable unless the feed happens to
    provide them.
    """

    def __init__(self, feed: BaseFeed) -> None:
        self._feed = feed

    async def fetch(self, symbol: str) -> SymbolFeed:
        bundle = await self._feed.get_market_data(symbol)
        liquidity = (bundle.liquidation_above + bundle.liquidation_below) > 0
        oi = len(bundle.oi_history) >= 2
        return SymbolFeed(bundle, FactorAvailability(liquidity=liquidity, oi=oi))


class CoinglassProvider:
    """Enriches ccxt bundles with Coinglass liquidation heatmap + realtime OI."""

    def __init__(self, feed: BaseFeed, coinglass: CoinglassClient) -> None:
        self._feed = feed
        self._cg = coinglass

    async def fetch(self, symbol: str) -> SymbolFeed:
        bundle = await self._feed.get_market_data(symbol)
        asset = _base_asset(symbol)
        try:
            heat = self._cg.get_liquidation_heatmap(asset)
            oi = self._cg.get_oi_realtime(asset)
        except Exception:
            logger.exception("coinglass fetch failed for %s — factors unavailable", asset)
            return SymbolFeed(bundle, FactorAvailability(liquidity=False, oi=False))

        # Shorts liquidate ABOVE price (fuel for up-moves); longs liquidate BELOW.
        liq_above = float(heat.get("shorts_liq_usd", 0) or 0)
        liq_below = float(heat.get("longs_liq_usd", 0) or 0)
        oi_series = _oi_series_from_realtime(oi)

        enriched = bundle.model_copy(
            update={
                "liquidation_above": liq_above,
                "liquidation_below": liq_below,
                "oi_history": oi_series or bundle.oi_history,
            }
        )
        availability = FactorAvailability(
            liquidity=(liq_above + liq_below) > 0,
            oi=len(oi_series) >= 2,
        )
        return SymbolFeed(enriched, availability)
