"""Backtest with REAL OI + Coinglass liquidation data.

Downloads:
- OHLCV from OKX REST API
- OI history from OKX
- Funding from OKX
- Liquidation levels from Coinglass

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
COINGLASS_KEY = "7abff9b1c52e41ddaff0d72ff2a8da09"


def okx_get(path: str, params: dict = None) -> dict:
    url = f"{BASE_URL}{path}"
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != "0":
        print(f"  API error: {data.get('msg', 'unknown')}")
    return data


def coinglass_get(path: str, params: dict = None) -> dict:
    url = f"https://open-api-v3.coinglass.com{path}"
    headers = {"accept": "application/json", "CG-API-KEY": COINGLASS_KEY}
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def download_candles_okx(inst_id: str, bar: str = "30m", limit: int = 1500) -> list[list]:
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
        for c in candles:
            all_candles.append([
                int(c[0]), float(c[1]), float(c[2]),
                float(c[3]), float(c[4]), float(c[5]), float(c[7]),
            ])
        after = candles[-1][0]
        print(f"{len(all_candles)}", end="..", flush=True)
        time.sleep(0.2)
    all_candles.sort(key=lambda c: c[0])
    seen = set()
    unique = [c for c in all_candles if c[0] not in seen and not seen.add(c[0])]
    print(f" total={len(unique)}")
    return unique


def download_oi_history(inst_id: str) -> list[dict]:
    print("Downloading OI history (OKX)...", end=" ", flush=True)
    all_oi = []
    after = ""
    while len(all_oi) < 1500:
        params = {"instId": inst_id, "period": "30m", "limit": "100"}
        if after:
            params["after"] = after
        data = okx_get("/api/v5/rubik/stat/contracts/open-interest-history", params)
        records = data.get("data", [])
        if not records:
            data = okx_get("/api/v5/public/open-interest", {"instId": inst_id})
            records = data.get("data", [])
            for r in records:
                all_oi.append({"ts": int(r.get("ts", 0)), "oi": float(r.get("oi", 0)), "oiCcy": float(r.get("oiCcy", 0))})
            break
        for r in records:
            all_oi.append({"ts": int(r.get("ts", 0)), "oi": float(r.get("oi", 0)), "oiCcy": float(r.get("oiCcy", 0))})
        after = records[-1].get("ts", "")
        print(f"{len(all_oi)}", end="..", flush=True)
        time.sleep(0.2)
    all_oi.sort(key=lambda x: x["ts"])
    print(f" total={len(all_oi)}")
    return all_oi


def download_funding_okx(inst_id: str) -> list[dict]:
    print("Downloading funding (OKX)...", end=" ", flush=True)
    all_rates = []
    after = ""
    while len(all_rates) < 500:
        params = {"instId": inst_id, "limit": "100"}
        if after:
            params["after"] = after
        data = okx_get("/api/v5/public/funding-rate-history", params)
        records = data.get("data", [])
        if not records:
            break
        for r in records:
            all_rates.append({"ts": int(r.get("fundingTime", 0)), "rate": float(r.get("fundingRate", 0))})
        after = records[-1].get("fundingTime", "")
        print(f"{len(all_rates)}", end="..", flush=True)
        time.sleep(0.2)
    all_rates.sort(key=lambda x: x["ts"])
    print(f" total={len(all_rates)}")
    return all_rates


def fetch_coinglass_data() -> dict:
    """Fetch liquidation and OI data from Coinglass."""
    print("Fetching Coinglass data...", end=" ", flush=True)
    result = {"liq_above": 0, "liq_below": 0, "oi_data": [], "ls_ratio": {}}

    # Liquidation info
    try:
        data = coinglass_get("/api/futures/liquidation/v2/info", {"symbol": "BTC"})
        info = data.get("data", {})
        if info:
            result["liq_info"] = info
            print("liq", end="..", flush=True)
    except Exception as e:
        print(f"liq_err:{e}", end="..", flush=True)

    # Aggregated OI
    try:
        data = coinglass_get("/api/futures/openInterest/ohlc-history", {
            "symbol": "BTC", "interval": "30m", "limit": "500",
        })
        oi_records = data.get("data", [])
        if isinstance(oi_records, list):
            result["oi_data"] = oi_records
            print(f"oi({len(oi_records)})", end="..", flush=True)
    except Exception as e:
        print(f"oi_err:{e}", end="..", flush=True)

    # Long/Short ratio
    try:
        data = coinglass_get("/api/futures/globalLongShortAccountRatio/chart", {
            "symbol": "BTC", "interval": "30m", "limit": "100",
        })
        result["ls_ratio"] = data.get("data", {})
        print("ls", end="..", flush=True)
    except Exception as e:
        print(f"ls_err:{e}", end="..", flush=True)

    # Funding across exchanges
    try:
        data = coinglass_get("/api/futures/funding/v2/current", {"symbol": "BTC"})
        result["funding_all"] = data.get("data", [])
        print("fund", end="..", flush=True)
    except Exception as e:
        print(f"fund_err:{e}", end="..", flush=True)

    print(" done")
    return result


def build_bundles(candles, oi_history, funding, coinglass_data):
    from app.models.market_data_bundle import MarketDataBundle
    from app.models.market_snapshot import MarketSnapshot

    print("Building bundles with REAL OI + Coinglass data...")

    oi_map = {}
    for r in oi_history:
        bucket = r["ts"] // (30 * 60 * 1000) * (30 * 60 * 1000)
        oi_map[bucket] = r.get("oiCcy", r.get("oi", 0))

    # Merge Coinglass OI if available
    cg_oi = coinglass_data.get("oi_data", [])
    for r in cg_oi:
        ts = int(r.get("t", r.get("ts", 0)))
        if ts > 0:
            bucket = ts // (30 * 60 * 1000) * (30 * 60 * 1000)
            oi_val = float(r.get("o", r.get("oi", 0)))
            if oi_val > 0:
                oi_map[bucket] = oi_val

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
        price = c[4]
        volume = c[6] if len(c) > 6 else c[5]
        spread = price * 0.0001

        snapshot = MarketSnapshot(
            symbol=CCXT_SYMBOL, price=price, volume=volume,
            bid=price - spread / 2, ask=price + spread / 2,
            timestamp=max(int(ts / 1000), 1),
        )

        start = max(0, i - history_size)
        price_history = [candles[j][4] for j in range(start, i + 1)]
        volume_history = [candles[j][6] if len(candles[j]) > 6 else candles[j][5] for j in range(start, i + 1)]

        oi_history_window = []
        for j in range(start, i + 1):
            bucket = candles[j][0] // (30 * 60 * 1000) * (30 * 60 * 1000)
            oi_val = oi_map.get(bucket, 0)
            if oi_val > 0:
                oi_history_window.append(oi_val)
        if not oi_history_window:
            oi_history_window = [0.0]

        candle_hour = ts // (3600 * 1000)
        funding_history = [r for h, r in sorted_funding if h <= candle_hour]
        if not funding_history:
            funding_history = [0.0]

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

    print(f"Built {len(bundles)} bundles")
    oi_coverage = sum(1 for b in bundles if b.oi_history[-1] > 0)
    print(f"OI coverage: {oi_coverage}/{len(bundles)} ({oi_coverage/max(len(bundles),1)*100:.0f}%)")
    return bundles


def run_backtest(bundles):
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

    configs = {
        "H2 + ALL FILTERS (normal)": OIDivergenceStrategy(
            symbol=CCXT_SYMBOL, inverse=False,
            require_volume_spike=True, require_oi_delta_neg=True,
        ),
        "H2 + ALL FILTERS (inverse)": OIDivergenceStrategy(
            symbol=CCXT_SYMBOL, inverse=True,
            require_volume_spike=True, require_oi_delta_neg=True,
        ),
        "H2 + RELAXED FILTERS (normal)": OIDivergenceStrategy(
            symbol=CCXT_SYMBOL, inverse=False,
            require_volume_spike=False, require_oi_delta_neg=False,
            min_volume_ratio=1.0, oi_threshold=-0.01,
        ),
    }

    print(f"\nBacktest: {len(bundles)} points | {LEVERAGE}x | {MARGIN_PCT*100:.0f}% margin")
    print(f"Filters: oi_delta + liquidation + spread + volume_spike + slippage")
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

    candles = download_candles_okx(SYMBOL, "30m", limit=1500)
    oi_history = download_oi_history(SYMBOL)
    funding = download_funding_okx(SYMBOL)
    coinglass_data = fetch_coinglass_data()

    with open("data/coinglass_data.json", "w") as f:
        json.dump(coinglass_data, f, indent=2, default=str)
    print(f"Saved Coinglass data")

    bundles = build_bundles(candles, oi_history, funding, coinglass_data)
    if bundles:
        run_backtest(bundles)
    else:
        print("ERROR: No bundles built")


if __name__ == "__main__":
    main()
