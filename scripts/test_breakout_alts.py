"""Test Breakout strategy on top-10 altcoins.

Assets: ETH, SOL, XRP, DOGE, ADA, AVAX, LINK, DOT, SUI, PEPE
Timeframe: 30min, 1500 candles
Leverage: 25x, Margin: 7%, SL: 1.0 ATR

Usage:
    python scripts/test_breakout_alts.py
"""
from __future__ import annotations
import os, sys, time
import requests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL = "https://www.okx.com"

SYMBOLS = [
    ("BTC-USDT-SWAP", "BTC/USDT:USDT"),
    ("ETH-USDT-SWAP", "ETH/USDT:USDT"),
    ("SOL-USDT-SWAP", "SOL/USDT:USDT"),
    ("XRP-USDT-SWAP", "XRP/USDT:USDT"),
    ("DOGE-USDT-SWAP", "DOGE/USDT:USDT"),
    ("ADA-USDT-SWAP", "ADA/USDT:USDT"),
    ("AVAX-USDT-SWAP", "AVAX/USDT:USDT"),
    ("LINK-USDT-SWAP", "LINK/USDT:USDT"),
    ("DOT-USDT-SWAP", "DOT/USDT:USDT"),
    ("SUI-USDT-SWAP", "SUI/USDT:USDT"),
    ("PEPE-USDT-SWAP", "PEPE/USDT:USDT"),
]

def okx_get(path, params=None):
    resp = requests.get(f"{BASE_URL}{path}", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()

def download_candles(inst_id, bar="30m", limit=1500):
    all_c = []
    after = ""
    while len(all_c) < limit:
        params = {"instId": inst_id, "bar": bar, "limit": "300"}
        if after: params["after"] = after
        try:
            data = okx_get("/api/v5/market/candles", params)
        except Exception:
            break
        candles = data.get("data", [])
        if not candles: break
        for c in candles:
            all_c.append([int(c[0]), float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5]), float(c[7])])
        after = candles[-1][0]
        time.sleep(0.2)
    all_c.sort(key=lambda c: c[0])
    seen = set()
    return [c for c in all_c if c[0] not in seen and not seen.add(c[0])]

def download_oi(inst_id):
    all_oi = []
    after = ""
    while len(all_oi) < 1500:
        params = {"instId": inst_id, "period": "30m", "limit": "100"}
        if after: params["after"] = after
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
            except Exception: pass
            break
        for r in records:
            if isinstance(r, dict):
                all_oi.append({"ts": int(r.get("ts", 0)), "oiCcy": float(r.get("oiCcy", 0))})
            elif isinstance(r, (list, tuple)) and len(r) >= 3:
                all_oi.append({"ts": int(r[0]), "oiCcy": float(r[2]) if len(r) > 2 else float(r[1])})
        if not all_oi: break
        after = str(all_oi[-1]["ts"])
        time.sleep(0.2)
    all_oi.sort(key=lambda x: x["ts"])
    return all_oi

def download_funding(inst_id):
    all_r = []
    after = ""
    while len(all_r) < 500:
        params = {"instId": inst_id, "limit": "100"}
        if after: params["after"] = after
        try:
            data = okx_get("/api/v5/public/funding-rate-history", params)
        except Exception: break
        records = data.get("data", [])
        if not records: break
        for r in records:
            if isinstance(r, dict):
                all_r.append({"ts": int(r.get("fundingTime", 0)), "rate": float(r.get("fundingRate", 0))})
        if not all_r: break
        after = records[-1].get("fundingTime", "") if isinstance(records[-1], dict) else ""
        if not after: break
        time.sleep(0.2)
    all_r.sort(key=lambda x: x["ts"])
    return all_r

def build_bundles(candles, oi_history, funding, symbol):
    from app.models.market_data_bundle import MarketDataBundle
    from app.models.market_snapshot import MarketSnapshot
    oi_map = {}
    for r in oi_history:
        bucket = r["ts"] // (30*60*1000) * (30*60*1000)
        oi_map[bucket] = r.get("oiCcy", 0)
    funding_map = {}
    for r in funding:
        funding_map[r["ts"] // (3600*1000)] = r["rate"]
    sorted_f = sorted(funding_map.items())
    hs = 50
    bundles = []
    for i in range(hs, len(candles)):
        c = candles[i]
        ts, price, vol = c[0], c[4], c[6] if len(c) > 6 else c[5]
        spread = price * 0.0002
        snap = MarketSnapshot(symbol=symbol, price=price, volume=vol,
            bid=price-spread/2, ask=price+spread/2, timestamp=max(int(ts/1000),1))
        start = max(0, i-hs)
        ph = [candles[j][4] for j in range(start, i+1)]
        vh = [candles[j][6] if len(candles[j])>6 else candles[j][5] for j in range(start, i+1)]
        oih = []
        for j in range(start, i+1):
            b = candles[j][0]//(30*60*1000)*(30*60*1000)
            v = oi_map.get(b, 0)
            if v > 0: oih.append(v)
        if not oih: oih = [0.0]
        ch = ts // (3600*1000)
        fh = [r for h, r in sorted_f if h <= ch]
        if not fh: fh = [0.0]
        bundles.append(MarketDataBundle(market=snap, price_history=ph, volume_history=vh,
            oi_history=oih, funding_history=fh, liquidation_above=price*1.02, liquidation_below=price*0.98))
    return bundles

def run_backtest(bundles, symbol):
    from app.analytics.feature_engine import FeatureEngine
    from app.backtest.engine import BacktestEngine, TPLevel
    from app.config import Settings
    from app.risk.risk_manager import RiskManager
    from app.strategy.breakout import BreakoutStrategy

    settings = Settings(account_equity=10_000.0, paper_trading=True, max_position_pct=0.07)
    tp_levels = [
        TPLevel(0.08, 0.40, True),   # TP1: +8% -> 40%, SL to entry
        TPLevel(0.25, 0.35, False),  # TP2: +25% -> 35%
        TPLevel(0.60, 1.0, False),   # TP3: +60% -> close rest
    ]
    engine = BacktestEngine(
        analytics=FeatureEngine(),
        strategy=BreakoutStrategy(symbol=symbol),
        risk=RiskManager(settings),
        initial_equity=10_000.0,
        leverage=25,
        max_position_pct=0.07,
        atr_risk_multiplier=1.0,
        tp_levels=tp_levels,
        trailing_stop_atr=0.0,
    )
    return engine.run(bundles)

def main():
    os.makedirs("data", exist_ok=True)

    print(f"{'='*100}")
    print(f"BREAKOUT STRATEGY: Top-10 Altcoins + BTC")
    print(f"Leverage: 25x | Margin: 7% | SL: 1.0 ATR | TF: 30min")
    print(f"TP: +8%(40%) -> +25%(35%) -> +60%(rest) | No trailing")
    print(f"{'='*100}")

    results = {}
    for okx_id, ccxt_id in SYMBOLS:
        short = ccxt_id.split("/")[0]
        print(f"\n[{short}] Downloading...", end=" ", flush=True)
        candles = download_candles(okx_id, "30m", 1500)
        print(f"{len(candles)}c", end="", flush=True)
        if len(candles) < 100:
            print(f" SKIP (not enough data)")
            continue
        oi = download_oi(okx_id)
        print(f" {len(oi)}oi", end="", flush=True)
        funding = download_funding(okx_id)
        print(f" {len(funding)}f", end="", flush=True)
        bundles = build_bundles(candles, oi, funding, ccxt_id)
        print(f" {len(bundles)}b", end="", flush=True)
        if not bundles:
            print(" SKIP (no bundles)")
            continue
        r = run_backtest(bundles, ccxt_id)
        results[short] = r
        pf = f"{r.profit_factor:.2f}" if r.profit_factor < 100 else "inf"
        print(f" -> {r.total_trades}tr WR={r.win_rate:.0%} PF={pf} Ret={r.total_return_pct:+.2f}%")

    # Summary table
    print(f"\n{'='*100}")
    print(f"{'Asset':<8} {'Trades':>6} {'WR':>6} {'PF':>7} {'Return':>8} {'MDD':>7} {'Sharpe':>7} {'Expect':>8} {'Equity':>10}")
    print(f"{'-'*100}")
    total_ret = 0
    profitable = 0
    for name in sorted(results, key=lambda x: results[x].total_return_pct, reverse=True):
        r = results[name]
        pf = f"{r.profit_factor:.2f}" if r.profit_factor < 100 else "inf"
        print(f"{name:<8} {r.total_trades:>6} {r.win_rate:>5.1%} {pf:>7} {r.total_return_pct:>+7.2f}% {r.max_drawdown_pct:>6.2f}% {r.sharpe_ratio:>7.2f} {r.expectancy:>+8.2f} ${r.final_equity:>9.2f}")
        total_ret += r.total_return_pct
        if r.total_return_pct > 0: profitable += 1
    print(f"{'-'*100}")
    avg = total_ret / len(results) if results else 0
    print(f"{'AVG':<8} {'':>6} {'':>6} {'':>7} {avg:>+7.2f}%")
    print(f"{'='*100}")
    if results:
        best = max(results.items(), key=lambda x: x[1].total_return_pct)
        worst = min(results.items(), key=lambda x: x[1].total_return_pct)
        print(f"\nBest:  {best[0]} ({best[1].total_return_pct:+.2f}%)")
        print(f"Worst: {worst[0]} ({worst[1].total_return_pct:+.2f}%)")
        print(f"Profitable: {profitable}/{len(results)} assets")

if __name__ == "__main__":
    main()
