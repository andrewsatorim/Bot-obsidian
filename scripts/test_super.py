"""Test SuperStrategy + OI Divergence on 30min and 15min timeframes.

All configs: Super s>=4, Super s>=3, OI Divergence, Breakout
Two runs: 30min and 15min

Usage:
    python scripts/test_super.py
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
COINGLASS_KEY = "7abff9b1c52e41ddaff0d72ff2a8da09"
CANDLE_LIMIT = 1500


def okx_get(path, params=None):
    resp = requests.get(f"{BASE_URL}{path}", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def coinglass_get(path, params=None):
    headers = {"accept": "application/json", "CG-API-KEY": COINGLASS_KEY}
    resp = requests.get(f"https://open-api-v3.coinglass.com{path}", headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def download_candles(inst_id, bar, limit):
    print(f"Downloading {limit} candles ({bar})...", end=" ", flush=True)
    all_c = []
    after = ""
    while len(all_c) < limit:
        params = {"instId": inst_id, "bar": bar, "limit": "300"}
        if after:
            params["after"] = after
        data = okx_get("/api/v5/market/candles", params)
        candles = data.get("data", [])
        if not candles:
            break
        for c in candles:
            all_c.append([int(c[0]), float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5]), float(c[7])])
        after = candles[-1][0]
        print(f"{len(all_c)}", end="..", flush=True)
        time.sleep(0.2)
    all_c.sort(key=lambda c: c[0])
    seen = set()
    unique = [c for c in all_c if c[0] not in seen and not seen.add(c[0])]
    print(f" total={len(unique)}")
    return unique


def download_oi(inst_id, period):
    print(f"Downloading OI ({period})...", end=" ", flush=True)
    all_oi = []
    after = ""
    while len(all_oi) < 1500:
        params = {"instId": inst_id, "period": period, "limit": "100"}
        if after:
            params["after"] = after
        try:
            data = okx_get("/api/v5/rubik/stat/contracts/open-interest-history", params)
        except Exception:
            break
        records = data.get("data", [])
        if not records:
            try:
                data2 = okx_get("/api/v5/public/open-interest", {"instId": inst_id})
                for r in data2.get("data", []):
                    if isinstance(r, dict):
                        all_oi.append({"ts": int(r.get("ts", 0)), "oiCcy": float(r.get("oiCcy", 0))})
            except Exception:
                pass
            break
        for r in records:
            if isinstance(r, dict):
                all_oi.append({"ts": int(r.get("ts", 0)), "oiCcy": float(r.get("oiCcy", 0))})
            elif isinstance(r, (list, tuple)) and len(r) >= 3:
                all_oi.append({"ts": int(r[0]), "oiCcy": float(r[2]) if len(r) > 2 else float(r[1])})
        if not all_oi:
            break
        after = str(all_oi[-1]["ts"])
        print(f"{len(all_oi)}", end="..", flush=True)
        time.sleep(0.2)
    all_oi.sort(key=lambda x: x["ts"])
    print(f" total={len(all_oi)}")
    return all_oi


def download_funding(inst_id):
    print("Downloading funding...", end=" ", flush=True)
    all_r = []
    after = ""
    while len(all_r) < 500:
        params = {"instId": inst_id, "limit": "100"}
        if after:
            params["after"] = after
        try:
            data = okx_get("/api/v5/public/funding-rate-history", params)
        except Exception:
            break
        records = data.get("data", [])
        if not records:
            break
        for r in records:
            if isinstance(r, dict):
                all_r.append({"ts": int(r.get("fundingTime", 0)), "rate": float(r.get("fundingRate", 0))})
        if not all_r:
            break
        after = records[-1].get("fundingTime", "") if isinstance(records[-1], dict) else ""
        if not after:
            break
        print(f"{len(all_r)}", end="..", flush=True)
        time.sleep(0.2)
    all_r.sort(key=lambda x: x["ts"])
    print(f" total={len(all_r)}")
    return all_r


def fetch_coinglass(interval):
    print(f"Fetching Coinglass ({interval})...", end=" ", flush=True)
    result = {"oi_data": []}
    try:
        data = coinglass_get("/api/futures/openInterest/ohlc-history",
                            {"symbol": "BTC", "interval": interval, "limit": "500"})
        oi = data.get("data", [])
        if isinstance(oi, list):
            result["oi_data"] = oi
            print(f"oi({len(oi)})", end="..", flush=True)
    except Exception as e:
        print(f"err:{e}", end="..", flush=True)
    print(" done")
    return result


def build_bundles(candles, oi_history, funding, cg_data, bucket_ms):
    from app.models.market_data_bundle import MarketDataBundle
    from app.models.market_snapshot import MarketSnapshot

    oi_map = {}
    for r in oi_history:
        bucket = r["ts"] // bucket_ms * bucket_ms
        oi_map[bucket] = r.get("oiCcy", 0)
    for r in cg_data.get("oi_data", []):
        if isinstance(r, dict):
            ts = int(r.get("t", r.get("ts", 0)))
            if ts > 0:
                bucket = ts // bucket_ms * bucket_ms
                val = float(r.get("o", r.get("oi", 0)))
                if val > 0:
                    oi_map[bucket] = val

    funding_map = {}
    for r in funding:
        funding_map[r["ts"] // (3600*1000)] = r["rate"]
    sorted_f = sorted(funding_map.items())

    hs = 50
    bundles = []
    for i in range(hs, len(candles)):
        c = candles[i]
        ts, price, vol = c[0], c[4], c[6] if len(c) > 6 else c[5]
        spread = price * 0.0001
        snap = MarketSnapshot(symbol=CCXT_SYMBOL, price=price, volume=vol,
            bid=price-spread/2, ask=price+spread/2, timestamp=max(int(ts/1000),1))
        start = max(0, i-hs)
        ph = [candles[j][4] for j in range(start, i+1)]
        vh = [candles[j][6] if len(candles[j])>6 else candles[j][5] for j in range(start, i+1)]
        oih = []
        for j in range(start, i+1):
            b = candles[j][0]//bucket_ms*bucket_ms
            v = oi_map.get(b, 0)
            if v > 0: oih.append(v)
        if not oih: oih = [0.0]
        ch = ts // (3600*1000)
        fh = [r for h, r in sorted_f if h <= ch]
        if not fh: fh = [0.0]
        bundles.append(MarketDataBundle(market=snap, price_history=ph, volume_history=vh,
            oi_history=oih, funding_history=fh, liquidation_above=price*1.02, liquidation_below=price*0.98))

    oi_cov = sum(1 for b in bundles if b.oi_history[-1] > 0)
    print(f"Built {len(bundles)} bundles (OI coverage: {oi_cov}/{len(bundles)})")
    return bundles


def run_test(bundles, tf_label, tf_minutes):
    from app.analytics.feature_engine import FeatureEngine
    from app.backtest.engine import BacktestEngine, TPLevel
    from app.config import Settings
    from app.risk.risk_manager import RiskManager
    from app.strategy.super_strategy import SuperStrategy
    from app.strategy.oi_divergence import OIDivergenceStrategy
    from app.strategy.breakout import BreakoutStrategy

    analytics = FeatureEngine()
    days = len(bundles) * tf_minutes / 60 / 24

    # Cooldown scales with timeframe
    cooldown_4h = int(4 * 60 / tf_minutes)   # 4 hours in bars
    cooldown_8h = int(8 * 60 / tf_minutes)   # 8 hours in bars

    configs = [
        {"name": "Super s>=4 m=7%",
         "strategy": SuperStrategy(symbol=CCXT_SYMBOL, cooldown_bars=cooldown_8h, min_score=4),
         "leverage": 25, "margin": 0.07, "atr_mult": 1.5,
         "tp_levels": [TPLevel(0.10, 0.30, True), TPLevel(0.50, 0.35, False), TPLevel(1.50, 1.0, False)],
         "trailing": 1.2},

        {"name": "Super s>=4 m=10%",
         "strategy": SuperStrategy(symbol=CCXT_SYMBOL, cooldown_bars=cooldown_8h, min_score=4),
         "leverage": 25, "margin": 0.10, "atr_mult": 1.5,
         "tp_levels": [TPLevel(0.10, 0.30, True), TPLevel(0.50, 0.35, False), TPLevel(1.50, 1.0, False)],
         "trailing": 1.2},

        {"name": "Super s>=3 m=7%",
         "strategy": SuperStrategy(symbol=CCXT_SYMBOL, cooldown_bars=cooldown_4h, min_score=3),
         "leverage": 25, "margin": 0.07, "atr_mult": 1.5,
         "tp_levels": [TPLevel(0.10, 0.30, True), TPLevel(0.50, 0.35, False), TPLevel(1.50, 1.0, False)],
         "trailing": 1.2},

        {"name": "OI Divergence 7%",
         "strategy": OIDivergenceStrategy(symbol=CCXT_SYMBOL, inverse=False,
             require_volume_spike=False, require_oi_delta_neg=True,
             oi_threshold=-0.02, min_strength=0.4, cooldown_bars=cooldown_4h),
         "leverage": 30, "margin": 0.07, "atr_mult": 1.5,
         "tp_levels": [TPLevel(0.1618, 0.0618, True), TPLevel(1.00, 0.1618, False), TPLevel(2.618, 0.50, False)],
         "trailing": 1.618},

        {"name": "OI Div relaxed 7%",
         "strategy": OIDivergenceStrategy(symbol=CCXT_SYMBOL, inverse=False,
             require_volume_spike=False, require_oi_delta_neg=False,
             oi_threshold=-0.01, min_strength=0.35, cooldown_bars=cooldown_4h),
         "leverage": 30, "margin": 0.07, "atr_mult": 1.5,
         "tp_levels": [TPLevel(0.1618, 0.0618, True), TPLevel(1.00, 0.1618, False), TPLevel(2.618, 0.50, False)],
         "trailing": 1.618},

        {"name": "Breakout 7%",
         "strategy": BreakoutStrategy(symbol=CCXT_SYMBOL),
         "leverage": 25, "margin": 0.07, "atr_mult": 1.0,
         "tp_levels": [TPLevel(0.08, 0.40, True), TPLevel(0.25, 0.35, False), TPLevel(0.60, 1.0, False)],
         "trailing": 0.0},
    ]

    print(f"\n{'#'*30} {tf_label} ({len(bundles)} candles = {days:.0f} days) {'#'*30}")
    print(f"\n{'='*100}")
    print(f"{'Strategy':<22} {'Trades':>6} {'WR':>6} {'PF':>7} {'Return':>8} {'MDD':>7} {'Sharpe':>7} {'Expect':>8} {'Equity':>10}")
    print(f"{'-'*100}")

    for cfg in configs:
        settings = Settings(account_equity=10_000.0, paper_trading=True, max_position_pct=cfg["margin"])
        engine = BacktestEngine(
            analytics=analytics, strategy=cfg["strategy"], risk=RiskManager(settings),
            initial_equity=10_000.0, leverage=cfg["leverage"], max_position_pct=cfg["margin"],
            atr_risk_multiplier=cfg["atr_mult"], tp_levels=cfg["tp_levels"], trailing_stop_atr=cfg["trailing"],
        )
        r = engine.run(bundles)
        pf = f"{r.profit_factor:.2f}" if r.profit_factor < 100 else "inf"
        print(f"{cfg['name']:<22} {r.total_trades:>6} {r.win_rate:>5.1%} {pf:>7}"
              f" {r.total_return_pct:>+7.2f}% {r.max_drawdown_pct:>6.2f}% {r.sharpe_ratio:>7.2f}"
              f" {r.expectancy:>+8.2f} ${r.final_equity:>9.2f}")

    print(f"{'='*100}")


def main():
    os.makedirs("data", exist_ok=True)
    funding = download_funding(SYMBOL)

    # === 30 MINUTE TEST ===
    print("\n" + "="*60)
    print("DOWNLOADING 30min DATA")
    print("="*60)
    candles_30m = download_candles(SYMBOL, "30m", CANDLE_LIMIT)
    oi_30m = download_oi(SYMBOL, "30m")
    cg_30m = fetch_coinglass("30m")
    bundles_30m = build_bundles(candles_30m, oi_30m, funding, cg_30m, 30*60*1000)
    if bundles_30m:
        run_test(bundles_30m, "30min", 30)

    # === 15 MINUTE TEST ===
    print("\n" + "="*60)
    print("DOWNLOADING 15min DATA")
    print("="*60)
    candles_15m = download_candles(SYMBOL, "15m", CANDLE_LIMIT)
    oi_15m = download_oi(SYMBOL, "15m")
    cg_15m = fetch_coinglass("15m")
    bundles_15m = build_bundles(candles_15m, oi_15m, funding, cg_15m, 15*60*1000)
    if bundles_15m:
        run_test(bundles_15m, "15min", 15)

    print("\n" + "="*60)
    print("DONE. Compare results above.")
    print("="*60)


if __name__ == "__main__":
    main()
