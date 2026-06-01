"""Unit tests for signal-engine market-data providers — no network, mocked clients."""

from __future__ import annotations

import asyncio

from app.models.market_data_bundle import MarketDataBundle
from app.models.market_snapshot import MarketSnapshot
from app.signal_engine.market_data import (
    CcxtOnlyProvider,
    CoinglassProvider,
)


def _bundle() -> MarketDataBundle:
    return MarketDataBundle(
        market=MarketSnapshot(
            symbol="NEAR/USDT:USDT", price=2.36, volume=1.0, bid=2.359, ask=2.361, timestamp=1
        ),
        price_history=[2.36],
        volume_history=[1.0],
        oi_history=[],  # ccxt typically gives <2 points
    )


class _StubFeed:
    async def get_market_data(self, symbol: str) -> MarketDataBundle:
        return _bundle()


class _StubCoinglass:
    """Deterministic Coinglass client — no HTTP."""

    def __init__(self, heat: dict, oi: dict, raise_exc: bool = False) -> None:
        self._heat = heat
        self._oi = oi
        self._raise = raise_exc
        self.calls: list[str] = []

    def get_liquidation_heatmap(self, symbol: str = "BTC") -> dict:
        self.calls.append(f"heat:{symbol}")
        if self._raise:
            raise RuntimeError("coinglass down")
        return self._heat

    def get_oi_realtime(self, symbol: str = "BTC") -> dict:
        self.calls.append(f"oi:{symbol}")
        if self._raise:
            raise RuntimeError("coinglass down")
        return self._oi


def test_ccxt_only_marks_liquidity_and_oi_unavailable() -> None:
    """With no Coinglass, the two data-dependent factors are flagged unavailable."""
    feed = CcxtOnlyProvider(_StubFeed())
    result = asyncio.run(feed.fetch("NEAR/USDT:USDT"))

    assert result.availability.liquidity is False
    assert result.availability.oi is False
    # The bundle is passed through unchanged (still no heatmap data).
    assert result.bundle.liquidation_above == 0.0
    assert result.bundle.liquidation_below == 0.0


def test_coinglass_enriches_bundle_and_flags_available() -> None:
    """Coinglass heatmap -> liquidation_above/below; realtime OI -> 2-point history."""
    heat = {"shorts_liq_usd": 8_500_000.0, "longs_liq_usd": 900_000.0}
    # OI grew 4% over the last hour -> reconstructed prev < now, oi rising.
    oi = {"total": {"oi_qty": 1_040.0, "change_1h": 4.0}}
    cg = _StubCoinglass(heat, oi)
    provider = CoinglassProvider(_StubFeed(), cg)

    result = asyncio.run(provider.fetch("NEAR/USDT:USDT"))

    # Coinglass uses the bare base asset.
    assert cg.calls == ["heat:NEAR", "oi:NEAR"]
    # Shorts liquidate above price, longs below.
    assert result.bundle.liquidation_above == 8_500_000.0
    assert result.bundle.liquidation_below == 900_000.0
    # Two-point OI history with the right (rising) order.
    assert len(result.bundle.oi_history) == 2
    assert result.bundle.oi_history[1] == 1_040.0
    assert result.bundle.oi_history[0] < result.bundle.oi_history[1]
    assert result.availability.liquidity is True
    assert result.availability.oi is True


def test_coinglass_failure_falls_back_to_unavailable() -> None:
    """If Coinglass raises, factors are unavailable — never fabricated as matched."""
    cg = _StubCoinglass({}, {}, raise_exc=True)
    provider = CoinglassProvider(_StubFeed(), cg)

    result = asyncio.run(provider.fetch("NEAR/USDT:USDT"))

    assert result.availability.liquidity is False
    assert result.availability.oi is False
    assert result.bundle.liquidation_above == 0.0  # untouched base bundle


def test_coinglass_zero_clusters_treated_as_unavailable() -> None:
    """Empty heatmap / zero OI -> unavailable, not a false 'no liquidity' verdict."""
    cg = _StubCoinglass(
        {"shorts_liq_usd": 0.0, "longs_liq_usd": 0.0},
        {"total": {"oi_qty": 0.0, "change_1h": 0.0}},
    )
    provider = CoinglassProvider(_StubFeed(), cg)

    result = asyncio.run(provider.fetch("NEAR/USDT:USDT"))

    assert result.availability.liquidity is False
    assert result.availability.oi is False
