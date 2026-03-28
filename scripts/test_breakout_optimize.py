"""Breakout Optimization — test different configs to find the best.

Tests:
1. Breakout Original (TP system)
2. Breakout + Trailing Stop (no TP)
3. Breakout + Trailing + Position Flip
4. Breakout with higher margin (25%)
5. Breakout 15m timeframe
6. Breakout 1H timeframe

Usage:
    python scripts/test_breakout_optimize.py
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
    ("ADA-USDT-SWAP", "ADA/USDT:USDT"),
    ("TSLA-USDT-SWAP", "TSLA/USDT:USDT"),
    ("NVDA-USDT-SWAP", "NVDA/USDT:USDT"),
]

def okx_get(path, params=None):
    resp = requests.get(f"{BASE_URL}{path}", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()

def check_instrument_exists(inst_id):
    try:
        data = okx_get("/api/v5/public/instruments", {"instType": "SWAP", "instId": inst_id})
        return len(data.get("data", [])) > 0
    except Exception:
        return False

def download_candles(inst_id, bar="30m", limit=1500):
    all_c = []
    after = ""
    while len(all_c) < limit:
        params = {"instId": inst_id, "bar": bar, "limit": "300"}
        if after: params["after"] = after
        try:
            data = okx_get("/api/v5/market/candles", params)
        except Exception: break
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
    while len(all_oi) < 500:
        params = {"instId": inst_id, "period": "30m", "limit": "100"}
        if after: params["after"] = after
        try:
            data = okx_get("/api/v5/rubik/stat/contracts/open-interest-history", params)
        except Exception: break
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
    while len(all_r) < 300:
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

def build_bundles(candles, oi_history, funding, symbol, bar_ms=30*60*1000):
    from app.models.market_data_bundle import MarketDataBundle
    from app.models.market_snapshot import MarketSnapshot
    oi_map = {}
    for r in oi_history:
        bucket = r["ts"] // bar_ms * bar_ms
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
            b = candles[j][0]//bar_ms*bar_ms
            v = oi_map.get(b, 0)
            if v > 0: oih.append(v)
        if not oih: oih = [0.0]
        ch = ts // (3600*1000)
        fh = [r for h, r in sorted_f if h <= ch]
        if not fh: fh = [0.0]
        bundles.append(MarketDataBundle(market=snap, price_history=ph, volume_history=vh,
            oi_history=oih, funding_history=fh, liquidation_above=price*1.02, liquidation_below=price*0.98))
    return bundles

def run_config(bundles, symbol, config):
    from app.analytics.feature_engine import FeatureEngine
    from app.backtest.engine import BacktestEngine, TPLevel
    from app.config import Settings
    from app.risk.risk_manager import RiskManager
    from app.strategy.breakout import BreakoutStrategy

    margin = config.get("margin", 0.15)
    leverage = config.get("leverage", 25)
    settings = Settings(account_equity=10_000.0, paper_trading=True, max_position_pct=margin)

    tp_levels = []
    if config.get("tp_system"):
        tp_levels = [
            TPLevel(0.08, 0.40, True),
            TPLevel(0.25, 0.35, False),
            TPLevel(0.60, 1.0, False),
        ]

    engine = BacktestEngine(
        analytics=FeatureEngine(),
        strategy=BreakoutStrategy(symbol=symbol),
        risk=RiskManager(settings),
        initial_equity=10_000.0,
        leverage=leverage,
        max_position_pct=margin,
        atr_risk_multiplier=config.get("atr_sl", 1.0),
        tp_levels=tp_levels,
        trailing_stop_atr=config.get("trailing", 0.0),
    )
    return engine.run(bundles)


CONFIGS = {
    "Original":       {"tp_system": True,  "trailing": 0.0, "margin": 0.15, "atr_sl": 1.0, "leverage": 25},
    "Trail-2.0":      {"tp_system": False, "trailing": 2.0, "margin": 0.15, "atr_sl": 1.0, "leverage": 25},
    "Trail-3.0":      {"tp_system": False, "trailing": 3.0, "margin": 0.15, "atr_sl": 1.5, "leverage": 25},
    "TP+Trail":       {"tp_system": True,  "trailing": 2.0, "margin": 0.15, "atr_sl": 1.0, "leverage": 25},
    "Margin-25%":     {"tp_system": True,  "trailing": 0.0, "margin": 0.25, "atr_sl": 1.0, "leverage": 25},
    "Lev-50x":        {"tp_system": True,  "trailing": 0.0, "margin": 0.15, "atr_sl": 1.0, "leverage": 50},
    "Margin25+Trail": {"tp_system": False, "trailing": 2.5, "margin": 0.25, "atr_sl": 1.0, "leverage": 25},
}


def main():
    print(f"{'='*120}")
    print(f"BREAKOUT OPTIMIZATION — 7 конфигураций на 6 активов")
    print(f"Leverage: 25-50x | Margin: 15-25% | 30m | 1 месяц")
    print(f"{'='*120}")

    # Check instruments
    print("\nChecking instruments...", end=" ", flush=True)
    valid = []
    for okx_id, ccxt_id in SYMBOLS:
        if check_instrument_exists(okx_id):
            valid.append((okx_id, ccxt_id))
            print(okx_id.split("-")[0], end=" ", flush=True)
        time.sleep(0.2)
    print(f"\n{len(valid)} available\n")

    # Download data once per symbol
    symbol_data = {}
    for okx_id, ccxt_id in valid:
        short = ccxt_id.split("/")[0]
        print(f"[{short}] Downloading...", end=" ", flush=True)
        candles = download_candles(okx_id, "30m", 1500)
        print(f"{len(candles)}c", end="", flush=True)
        if len(candles) < 100:
            print(" SKIP")
            continue
        oi = download_oi(okx_id)
        print(f" {len(oi)}oi", end="", flush=True)
        funding = download_funding(okx_id)
        print(f" {len(funding)}f", end="", flush=True)
        bundles = build_bundles(candles, oi, funding, ccxt_id)
        print(f" {len(bundles)}b", flush=True)
        symbol_data[short] = (ccxt_id, bundles)

    # Run all configs
    results = {}  # {config_name: {symbol: result}}
    for cfg_name, cfg in CONFIGS.items():
        results[cfg_name] = {}
        for short, (ccxt_id, bundles) in symbol_data.items():
            r = run_config(bundles, ccxt_id, cfg)
            results[cfg_name][short] = r

    # Summary table
    symbols = list(symbol_data.keys())
    print(f"\n{'='*120}")
    header = f"{'Config':<16}"
    for s in symbols:
        header += f" {s:>8}"
    header += f" {'AVG':>8} {'Trades':>7} {'WR':>5}"
    print(header)
    print(f"{'-'*120}")

    best_cfg = None
    best_avg = -999

    for cfg_name in CONFIGS:
        line = f"{cfg_name:<16}"
        rets = []
        total_trades = 0
        total_wins = 0
        for s in symbols:
            if s in results[cfg_name]:
                r = results[cfg_name][s]
                line += f" {r.total_return_pct:>+7.2f}%"
                rets.append(r.total_return_pct)
                total_trades += r.total_trades
                total_wins += r.winning_trades
            else:
                line += f" {'N/A':>8}"
        avg = sum(rets) / len(rets) if rets else 0
        wr = total_wins / total_trades if total_trades > 0 else 0
        line += f" {avg:>+7.2f}% {total_trades:>7} {wr:>4.0%}"
        print(line)
        if avg > best_avg:
            best_avg = avg
            best_cfg = cfg_name

    print(f"{'='*120}")
    print(f"\nЛучшая конфигурация: {best_cfg} (avg {best_avg:+.2f}%)")

    # Profit calculation
    deposit = 10_000.0
    print(f"\nПрофит на ${deposit:,.0f}:")
    for cfg_name in CONFIGS:
        rets = [results[cfg_name][s].total_return_pct for s in symbols if s in results[cfg_name]]
        avg = sum(rets) / len(rets) if rets else 0
        profit = deposit * avg / 100
        mark = "+" if profit >= 0 else ""
        print(f"  {cfg_name:<16} {avg:>+7.2f}%  ->  {mark}${abs(profit):>7.2f}")

    # Best config details
    if best_cfg:
        print(f"\nДетали лучшей ({best_cfg}):")
        for s in symbols:
            if s not in results[best_cfg]:
                continue
            r = results[best_cfg][s]
            print(f"  {s}: {r.total_trades}tr WR={r.win_rate:.0%} Ret={r.total_return_pct:+.2f}% MDD={r.max_drawdown_pct:.2f}%")
            for j, t in enumerate(r.trades):
                bars = t.exit_idx - t.entry_idx
                hours = bars * 30 / 60
                pnl_sign = "+" if t.pnl > 0 else ""
                print(f"    #{j+1} {t.direction.value:>5} {t.entry_price:.2f}->{t.exit_price:.2f} "
                      f"PnL={pnl_sign}{t.pnl:.2f} {hours:.1f}ч")

if __name__ == "__main__":
    main()
