"""Test Donchian Channel Breakout (Turtle Trading) on 4H.

Usage:
    python scripts/test_donchian.py
"""
from __future__ import annotations
import os, sys, time
import requests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL = "https://www.okx.com"

SYMBOLS = [
    ("BTC-USDT-SWAP", "BTC/USDT:USDT", "Crypto"),
    ("ETH-USDT-SWAP", "ETH/USDT:USDT", "Crypto"),
    ("SOL-USDT-SWAP", "SOL/USDT:USDT", "Crypto"),
    ("ADA-USDT-SWAP", "ADA/USDT:USDT", "Crypto"),
    ("TSLA-USDT-SWAP", "TSLA/USDT:USDT", "Stock"),
    ("NVDA-USDT-SWAP", "NVDA/USDT:USDT", "Stock"),
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

def download_candles(inst_id, bar="4H", limit=1500):
    """Download 4H candles — 1500 candles = ~250 days."""
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
    while len(all_oi) < 500:
        params = {"instId": inst_id, "period": "4H", "limit": "100"}
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
        bucket = r["ts"] // (4*3600*1000) * (4*3600*1000)
        oi_map[bucket] = r.get("oiCcy", 0)
    funding_map = {}
    for r in funding:
        funding_map[r["ts"] // (3600*1000)] = r["rate"]
    sorted_f = sorted(funding_map.items())
    hs = 30  # 30 bars * 4h = 5 days lookback
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
            b = candles[j][0]//(4*3600*1000)*(4*3600*1000)
            v = oi_map.get(b, 0)
            if v > 0: oih.append(v)
        if not oih: oih = [0.0]
        ch = ts // (3600*1000)
        fh = [r for h, r in sorted_f if h <= ch]
        if not fh: fh = [0.0]
        bundles.append(MarketDataBundle(market=snap, price_history=ph, volume_history=vh,
            oi_history=oih, funding_history=fh, liquidation_above=price*1.03, liquidation_below=price*0.97))
    return bundles

def run_backtest(bundles, symbol):
    from app.analytics.feature_engine import FeatureEngine
    from app.backtest.engine import BacktestEngine
    from app.config import Settings
    from app.risk.risk_manager import RiskManager
    from app.strategy.donchian import DonchianStrategy
    settings = Settings(account_equity=10_000.0, paper_trading=True, max_position_pct=0.15)
    engine = BacktestEngine(
        analytics=FeatureEngine(),
        strategy=DonchianStrategy(symbol=symbol, channel_period=20),
        risk=RiskManager(settings),
        initial_equity=10_000.0,
        leverage=25,
        max_position_pct=0.15,
        atr_risk_multiplier=2.0,
        tp_levels=[],              # NO TP — trailing stop rides the trend
        trailing_stop_atr=3.0,     # wide trailing on 4h
    )
    return engine.run(bundles)

def main():
    os.makedirs("data", exist_ok=True)

    print(f"{'='*110}")
    print(f"DONCHIAN CHANNEL BREAKOUT (Turtle Trading)")
    print(f"LONG on 20-period high break | SHORT on 20-period low break")
    print(f"Timeframe: 4H | Leverage: 25x | Margin: 15% | SL: 2.0 ATR | Trailing: 3.0 ATR | NO TP")
    print(f"{'='*110}")

    print("\nChecking available instruments...", end=" ", flush=True)
    valid_symbols = []
    for okx_id, ccxt_id, asset_class in SYMBOLS:
        exists = check_instrument_exists(okx_id)
        if exists:
            valid_symbols.append((okx_id, ccxt_id, asset_class))
            print(f"{okx_id.split('-')[0]}", end=" ", flush=True)
        else:
            print(f"[{okx_id.split('-')[0]}:N/A]", end=" ", flush=True)
        time.sleep(0.2)
    print(f"\n{len(valid_symbols)} instruments available\n")

    results = {}
    for okx_id, ccxt_id, asset_class in valid_symbols:
        short = ccxt_id.split("/")[0]
        label = f"{short} ({asset_class})"
        print(f"[{label}] Downloading 4H...", end=" ", flush=True)
        candles = download_candles(okx_id, "4H", 1500)
        print(f"{len(candles)}c", end="", flush=True)
        if len(candles) < 60:
            print(f" SKIP (need 60+)")
            continue
        oi = download_oi(okx_id)
        print(f" {len(oi)}oi", end="", flush=True)
        funding = download_funding(okx_id)
        print(f" {len(funding)}f", end="", flush=True)
        bundles = build_bundles(candles, oi, funding, ccxt_id)
        print(f" {len(bundles)}b", end="", flush=True)
        if not bundles:
            print(" SKIP")
            continue
        # Show date range
        from datetime import datetime
        first_ts = candles[0][0] / 1000
        last_ts = candles[-1][0] / 1000
        first_date = datetime.utcfromtimestamp(first_ts).strftime("%Y-%m-%d")
        last_date = datetime.utcfromtimestamp(last_ts).strftime("%Y-%m-%d")
        days = (last_ts - first_ts) / 86400
        print(f" [{first_date} -> {last_date}] ({days:.0f}д)", end="", flush=True)

        r = run_backtest(bundles, ccxt_id)
        results[label] = r
        pf = f"{r.profit_factor:.2f}" if r.profit_factor < 100 else "inf"
        print(f" -> {r.total_trades}tr WR={r.win_rate:.0%} PF={pf} Ret={r.total_return_pct:+.2f}%")

    # Summary
    print(f"\n{'='*110}")
    print(f"{'Asset':<20} {'Class':<8} {'Trades':>6} {'WR':>6} {'PF':>7} {'Return':>8} {'MDD':>7} {'Sharpe':>7} {'Equity':>10}")
    print(f"{'-'*110}")
    total_ret = 0
    profitable = 0
    for name in sorted(results, key=lambda x: results[x].total_return_pct, reverse=True):
        r = results[name]
        cls = name.split("(")[1].rstrip(")") if "(" in name else "?"
        pf = f"{r.profit_factor:.2f}" if r.profit_factor < 100 else "inf"
        print(f"{name:<20} {cls:<8} {r.total_trades:>6} {r.win_rate:>5.1%} {pf:>7} {r.total_return_pct:>+7.2f}% {r.max_drawdown_pct:>6.2f}% {r.sharpe_ratio:>7.2f} ${r.final_equity:>9.2f}")
        total_ret += r.total_return_pct
        if r.total_return_pct > 0: profitable += 1

    avg = total_ret / len(results) if results else 0
    print(f"{'-'*110}")
    print(f"{'TOTAL AVG':<20} {'':>8} {'':>6} {'':>6} {'':>7} {avg:>+7.2f}%")
    print(f"{'='*110}")

    if results:
        best = max(results.items(), key=lambda x: x[1].total_return_pct)
        worst = min(results.items(), key=lambda x: x[1].total_return_pct)
        print(f"\nBest:  {best[0]} ({best[1].total_return_pct:+.2f}%)")
        print(f"Worst: {worst[0]} ({worst[1].total_return_pct:+.2f}%)")
        print(f"Profitable: {profitable}/{len(results)} assets")

        # --- TRADE DETAILS ---
        print(f"\n{'='*110}")
        print(f"СДЕЛКИ (каждая свеча = 4 часа)")
        print(f"{'='*110}")
        for name in sorted(results, key=lambda x: results[x].total_return_pct, reverse=True):
            r = results[name]
            if not r.trades:
                print(f"  {name}: нет сделок")
                continue
            print(f"  {name}:")
            for j, t in enumerate(r.trades):
                bars = t.exit_idx - t.entry_idx
                hours = bars * 4
                days = hours / 24
                direction = t.direction.value
                pnl_sign = "+" if t.pnl > 0 else ""
                dur_str = f"{days:.1f}д ({hours}ч)" if days >= 1 else f"{hours}ч ({bars} свечей)"
                print(f"    #{j+1} {direction:>5} вход={t.entry_price:.2f} выход={t.exit_price:.2f} "
                      f"PnL={pnl_sign}{t.pnl:.2f} длит={dur_str}")
            avg_bars = sum(t.exit_idx - t.entry_idx for t in r.trades) / len(r.trades)
            avg_days = avg_bars * 4 / 24
            print(f"    Среднее: {avg_days:.1f}д ({avg_bars:.0f} свечей)")
        print(f"{'='*110}")

        # --- PROFIT ---
        deposit = 10_000.0
        print(f"\n{'='*110}")
        print(f"РАСЧЁТ ПРОФИТА НА ДЕПОЗИТ ${deposit:,.0f}")
        print(f"{'='*110}")
        total_profit = 0
        for name in sorted(results, key=lambda x: results[x].total_return_pct, reverse=True):
            r = results[name]
            profit = deposit * r.total_return_pct / 100
            total_profit += profit
            final = deposit + profit
            mark = "+" if profit >= 0 else ""
            print(f"  {name:<20} {r.total_return_pct:>+7.2f}%  ->  {mark}${abs(profit):>8.2f}  (итого ${final:>10.2f})")
        avg_profit = deposit * avg / 100
        print(f"{'-'*110}")
        print(f"  {'СРЕДНИЙ RETURN':<20} {avg:>+7.2f}%  ->  +${avg_profit:>8.2f}  (итого ${deposit + avg_profit:>10.2f})")
        print(f"{'='*110}")

if __name__ == "__main__":
    main()
