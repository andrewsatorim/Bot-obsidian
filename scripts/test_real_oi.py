"""Backtest with REAL OI data from OKX REST API (no auth needed).

Downloads: OHLCV (30min) + Open Interest history + Funding rate history
All via OKX public API v5.

Usage:
    python scripts/test_real_oi.py
"""
from __future__ import annotations

import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SYMBOL = "BTC-USDT-SWAP"
CCXT_SYMBOL = "BTC/USDT:USDT"
BASE_URL = "https://www.okx.com"
LEVERAGE = 30
MARGIN_PCT = 0.07


def okx_get(path: str, params: dict = None) -> dict:
    """Make OKX public API request."""
    url = f"{BASE_URL}{path}"
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != "0":
        print(f"  API error: {data.get('msg', 'unknown')}")
    return data


def download_candles_okx(inst_id: str, bar: str = "30m", limit: int = 1500) -> list[list]:
    """Download OHLCV via OKX REST API with pagination."""
    print(f"Downloading {limit} candles ({bar})...", end=" ", flush=True)
    all_candles = []
    after = ""

    while len(all_candles) < limit:
        params = {"instId": inst_id, "bar": bar, "limit": "300"}
        if after:
            params["after"] = after

        data = okx_get("/api/v5/market/candles", params)
        candles = data.get("data", [])
        if not candles:
            break

        # OKX format: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
        for c in candles:
            all_candles.append([
                int(c[0]),       # timestamp ms
                float(c[1]),     # open
                float(c[2]),     # high
                float(c[3]),     # low
                float(c[4]),     # close
                float(c[5]),     # vol (contracts)
                float(c[7]),     # volCcyQuote (USDT volume)
            ])

        after = candles[-1][0]  # Oldest timestamp for next page
        print(f"{len(all_candles)}", end="..", flush=True)
        time.sleep(0.2)

    all_candles.sort(key=lambda c: c[0])
    # Deduplicate
    seen = set()
    unique = []
    for c in all_candles:
        if c[0] not in seen:
            seen.add(c[0])
            unique.append(c)
    print(f" total={len(unique)}")
    return unique


def download_oi_history(inst_id: str, period: str = "30m", limit: int = 1500) -> list[dict]:
    """Download Open Interest history via OKX REST API."""
    print(f"Downloading OI history...", end=" ", flush=True)
    all_oi = []
    after = ""

    while len(all_oi) < limit:
        params = {"instId": inst_id, "period": period, "limit": "100"}
        if after:
            params["after"] = after

        data = okx_get("/api/v5/rubik/stat/contracts/open-interest-history", params)
        records = data.get("data", [])
        if not records:
            # Try alternative endpoint
            data = okx_get("/api/v5/public/open-interest", {"instId": inst_id})
            records = data.get("data", [])
            if records:
                for r in records:
                    all_oi.append({
                        "ts": int(r.get("ts", 0)),
                        "oi": float(r.get("oi", 0)),
                        "oiCcy": float(r.get("oiCcy", 0)),
                    })
            break

        for r in records:
            all_oi.append({
                "ts": int(r.get("ts", 0)),
                "oi": float(r.get("oi", 0)),
                "oiCcy": float(r.get("oiCcy", 0)),
            })

        after = records[-1].get("ts", "")
        print(f"{len(all_oi)}", end="..", flush=True)
        time.sleep(0.2)

    all_oi.sort(key=lambda x: x["ts"])
    print(f" total={len(all_oi)}")
    return all_oi


def download_funding_okx(inst_id: str, limit: int = 500) -> list[dict]:
    """Download funding rate history via OKX REST API."""
    print(f"Downloading funding history...", end=" ", flush=True)
    all_rates = []
    after = ""

    while len(all_rates) < limit:
        params = {"instId": inst_id, "limit": "100"}
        if after:
            params["after"] = after

        data = okx_get("/api/v5/public/funding-rate-history", params)
        records = data.get("data", [])
        if not records:
            break

        for r in records:
            all_rates.append({
                "ts": int(r.get("fundingTime", 0)),
                "rate": float(r.get("fundingRate", 0)),
                "realizedRate": float(r.get("realizedRate", 0)),
            })

        after = records[-1].get("fundingTime", "")
        print(f"{len(all_rates)}", end="..", flush=True)
        time.sleep(0.2)

    all_rates.sort(key=lambda x: x["ts"])
    print(f" total={len(all_rates)}")
    return all_rates


def download_liquidations(inst_id: str) -> dict:
    """Get current liquidation levels (approximation from mark price + OI)."""
    data = okx_get("/api/v5/public/mark-price", {"instId": inst_id})
    mark = float(data["data"][0]["markPx"]) if data.get("data") else 0

    data = okx_get("/api/v5/public/open-interest", {"instId": inst_id})
    oi = float(data["data"][0]["oi"]) if data.get("data") else 0

    # Approximate liquidation clusters at +/-2% and +/-5% from mark price
    return {
        "mark_price": mark,
        "oi": oi,
        "liq_above": mark * 1.02,  # Short liquidation zone
        "liq_below": mark * 0.98,  # Long liquidation zone
    }


def build_bundles(candles: list, oi_history: list, funding: list):
    """Build MarketDataBundles with REAL OI data."""
    from app.models.market_data_bundle import MarketDataBundle
    from app.models.market_snapshot import MarketSnapshot

    print("Building bundles with REAL OI data...")

    # Build OI lookup: timestamp -> oi value
    oi_map = {}
    for r in oi_history:
        # Round to 30min bucket
        bucket = r["ts"] // (30 * 60 * 1000) * (30 * 60 * 1000)
        oi_map[bucket] = r.get("oiCcy", r.get("oi", 0))

    # Build funding lookup
    funding_map = {}
    for r in funding:
        hour_key = r["ts"] // (3600 * 1000)
        funding_map[hour_key] = r["rate"]
    sorted_funding = sorted(funding_map.items())

    history_size = 50
    bundles = []

    for i in range(history_size, len(candles)):
        c = candles[i]
        ts = c[0]
        price = c[4]  # close
        volume = c[6] if len(c) > 6 else c[5]  # USDT volume if available
        spread = price * 0.0001

        snapshot = MarketSnapshot(
            symbol=CCXT_SYMBOL,
            price=price,
            volume=volume,
            bid=price - spread / 2,
            ask=price + spread / 2,
            timestamp=max(int(ts / 1000), 1),
        )

        start = max(0, i - history_size)
        price_history = [candles[j][4] for j in range(start, i + 1)]
        volume_history = [candles[j][6] if len(candles[j]) > 6 else candles[j][5] for j in range(start, i + 1)]

        # REAL OI history from downloaded data
        oi_history_window = []
        for j in range(start, i + 1):
            bucket = candles[j][0] // (30 * 60 * 1000) * (30 * 60 * 1000)
            oi_val = oi_map.get(bucket, 0)
            if oi_val > 0:
                oi_history_window.append(oi_val)
        if not oi_history_window:
            oi_history_window = [0.0]

        # Funding history
        candle_hour = ts // (3600 * 1000)
        funding_history = [r for h, r in sorted_funding if h <= candle_hour]
        if not funding_history:
            funding_history = [0.0]

        # Liquidation levels (approximate)
        liq_above = price * 1.02
        liq_below = price * 0.98

        bundles.append(MarketDataBundle(
            market=snapshot,
            price_history=price_history,
            volume_history=volume_history,
            oi_history=oi_history_window,
            funding_history=funding_history,
            liquidation_above=liq_above,
            liquidation_below=liq_below,
        ))

    print(f"Built {len(bundles)} bundles with real OI")
    oi_coverage = sum(1 for b in bundles if b.oi_history[-1] > 0)
    print(f"OI data coverage: {oi_coverage}/{len(bundles)} ({oi_coverage/max(len(bundles),1)*100:.0f}%)")
    return bundles


def run_backtest(bundles):
    """Run H2 with real data."""
    from app.analytics.feature_engine import FeatureEngine
    from app.backtest.engine import BacktestEngine, TPLevel
    from app.config import Settings
    from app.risk.risk_manager import RiskManager
    from app.strategy.oi_divergence import OIDivergenceStrategy

    settings = Settings(account_equity=10_000.0, paper_trading=True, max_position_pct=MARGIN_PCT)

    h2_levels = [
        TPLevel(pnl_pct=0.1618, close_pct=0.0618, move_sl_to_entry=True),
        TPLevel(pnl_pct=1.00,   close_pct=0.1618, move_sl_to_entry=False),
        TPLevel(pnl_pct=2.618,  close_pct=0.50,   move_sl_to_entry=False),
    ]

    # Test both normal and inverse
    configs = {
        "H2 Normal (OI Divergence)": OIDivergenceStrategy(symbol=CCXT_SYMBOL, inverse=False),
        "H2 Inverse (trend-follow)": OIDivergenceStrategy(symbol=CCXT_SYMBOL, inverse=True),
    }

    print(f"\nBacktest: {len(bundles)} points | {LEVERAGE}x | {MARGIN_PCT*100:.0f}% margin")
    print("=" * 70)

    for name, strategy in configs.items():
        engine = BacktestEngine(
            analytics=FeatureEngine(),
            strategy=strategy,
            risk=RiskManager(settings),
            initial_equity=10_000.0,
            leverage=LEVERAGE,
            max_position_pct=MARGIN_PCT,
            tp_levels=h2_levels,
            trailing_stop_atr=1.618,
        )
        result = engine.run(bundles)
        print(f"\n--- {name} ---")
        print(result.summary())
        print()

    print("=" * 70)


def main():
    os.makedirs("data", exist_ok=True)

    # Download all data
    candles = download_candles_okx(SYMBOL, "30m", limit=1500)
    oi_history = download_oi_history(SYMBOL, "30m", limit=1500)
    funding = download_funding_okx(SYMBOL, limit=500)
    liq = download_liquidations(SYMBOL)

    print(f"\nCurrent: price=${liq['mark_price']:,.2f} OI={liq['oi']:,.0f} contracts")
    print(f"Liq zones: above=${liq['liq_above']:,.0f} below=${liq['liq_below']:,.0f}")

    # Save raw data
    with open("data/okx_real_oi.json", "w") as f:
        json.dump({"candles": len(candles), "oi": len(oi_history), "funding": len(funding)}, f)

    # Build and test
    bundles = build_bundles(candles, oi_history, funding)
    if bundles:
        run_backtest(bundles)
    else:
        print("ERROR: No bundles built")


if __name__ == "__main__":
    main()
