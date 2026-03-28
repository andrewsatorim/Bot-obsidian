"""Breakout+Flip on MEXC with Coinglass OI — ALL crypto pairs.

Uses MEXC for candle data + Coinglass V4 for OI data.
This is the proven combo: Breakout+Flip needs OI filter to work.

Usage:
    python scripts/test_mexc_coinglass.py
"""
from __future__ import annotations
import os, sys, time
import requests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MEXC_BASE = "https://contract.mexc.com"
CG_BASE = "https://open-api-v4.coinglass.com"
CG_KEY = "ce8e53d9a000432bbd0bafa1bc4e9171"

# Top crypto + all non-crypto on MEXC
SYMBOLS = {
    # CRYPTO TOP-15
    "BTC": ("BTC_USDT", "Crypto"),
    "ETH": ("ETH_USDT", "Crypto"),
    "SOL": ("SOL_USDT", "Crypto"),
    "XRP": ("XRP_USDT", "Crypto"),
    "DOGE": ("DOGE_USDT", "Crypto"),
    "ADA": ("ADA_USDT", "Crypto"),
    "AVAX": ("AVAX_USDT", "Crypto"),
    "LINK": ("LINK_USDT", "Crypto"),
    "DOT": ("DOT_USDT", "Crypto"),
    "SUI": ("SUI_USDT", "Crypto"),
    "NEAR": ("NEAR_USDT", "Crypto"),
    "PEPE": ("PEPE_USDT", "Crypto"),
    "ARB": ("ARB_USDT", "Crypto"),
    "OP": ("OP_USDT", "Crypto"),
    "INJ": ("INJ_USDT", "Crypto"),
    # NON-CRYPTO
    "GOLD": ("XAUT_USDT", "Gold"),
    "SILVER": ("SILVER_USDT", "Silver"),
    "WTI": ("USOIL_USDT", "Oil"),
    "BRENT": ("UKOIL_USDT", "Oil"),
    "SP500": ("SP500_USDT", "Index"),
    "NAS100": ("NAS100_USDT", "Index"),
    "US30": ("US30_USDT", "Index"),
    "TSLA": ("TSLA_USDT", "Stock"),
    "NVDA": ("NVDA_USDT", "Stock"),
    "AAPL": ("AAPL_USDT", "Stock"),
    "META": ("META_USDT", "Stock"),
    "MSFT": ("MSFT_USDT", "Stock"),
    "GOOGL": ("GOOGL_USDT", "Stock"),
    "AMZN": ("AMZN_USDT", "Stock"),
    "COIN": ("COIN_USDT", "Stock"),
    "MSTR": ("MSTR_USDT", "Stock"),
    "AMD": ("AMD_USDT", "Stock"),
    "MU": ("MU_USDT", "Stock"),
    "HOOD": ("HOOD_USDT", "Stock"),
}

def mexc_get(path, params=None):
    r = requests.get(f"{MEXC_BASE}{path}", params=params, timeout=15)
    r.raise_for_status()
    return r.json()

def cg_get(path, params=None):
    """Coinglass V4 API call."""
    headers = {"CG-API-KEY": CG_KEY, "accept": "application/json"}
    r = requests.get(f"{CG_BASE}{path}", params=params, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()

# ============ DATA DOWNLOAD ============

def dl_mexc_candles(symbol, interval="Min30", limit=1500):
    all_c = []
    end = int(time.time())
    for _ in range(10):
        try:
            data = mexc_get(f"/api/v1/contract/kline/{symbol}", {
                "interval": interval, "start": end - 300 * 1800, "end": end,
            })
        except: break
        d = data.get("data", {})
        times = d.get("time", [])
        if not times: break
        opens, highs = d.get("open", []), d.get("high", [])
        lows, closes, vols = d.get("low", []), d.get("close", []), d.get("vol", [])
        batch = []
        for i in range(len(times)):
            ts = int(times[i]) * 1000 if times[i] < 1e12 else int(times[i])
            batch.append([ts, float(opens[i]), float(highs[i]), float(lows[i]),
                         float(closes[i]), float(vols[i]), float(vols[i])])
        if not batch: break
        before = len(all_c)
        all_c.extend(batch)
        seen = set()
        all_c = [c for c in all_c if c[0] not in seen and not seen.add(c[0])]
        if len(all_c) >= limit or len(all_c) == before: break
        end = min(c[0] for c in batch) // 1000 - 1
        time.sleep(0.3)
    all_c.sort(key=lambda c: c[0])
    return all_c

def dl_coinglass_oi(symbol, interval="30min", limit=500):
    """Download OI history from Coinglass V4 via Binance exchange."""
    all_oi = []
    try:
        data = cg_get("/api/futures/open-interest/history", {
            "exchange": "Binance", "symbol": symbol,
            "interval": interval, "limit": str(limit),
        })
        if data.get("code") == "0" and data.get("data"):
            for item in data["data"]:
                ts = int(item.get("time", 0))
                # OI values are strings
                close_oi = float(item.get("close", 0))
                all_oi.append({"ts": ts, "oiCcy": close_oi})
    except Exception as e:
        pass

    # Also try getting real-time OI change for current signal
    try:
        rt = cg_get("/api/futures/open-interest/exchange-list", {"symbol": symbol})
        if rt.get("code") == "0" and rt.get("data"):
            for item in rt["data"]:
                if item.get("exchange") == "All":
                    # Store aggregated change percentages
                    all_oi.append({
                        "ts": int(time.time() * 1000),
                        "oiCcy": float(item.get("open_interest_quantity", 0)),
                        "change_5m": float(item.get("open_interest_change_percent_5m", 0)),
                        "change_1h": float(item.get("open_interest_change_percent_1h", 0)),
                        "change_4h": float(item.get("open_interest_change_percent_4h", 0)),
                    })
                    break
    except: pass

    all_oi.sort(key=lambda x: x["ts"])
    time.sleep(2.5)  # Coinglass rate limit: 30 req/min
    return all_oi

# ============ BUILD & BACKTEST ============

def build_bundles(candles, oi_history, symbol):
    from app.models.market_data_bundle import MarketDataBundle
    from app.models.market_snapshot import MarketSnapshot
    oi_map = {}
    for r in oi_history:
        bucket = r["ts"] // (30*60*1000) * (30*60*1000)
        if r.get("oiCcy", 0) > 0:
            oi_map[bucket] = r["oiCcy"]
    hs = 50
    bundles = []
    for i in range(hs, len(candles)):
        c = candles[i]
        ts, price, vol = c[0], c[4], c[6]
        sp = price * 0.0003
        snap = MarketSnapshot(symbol=symbol, price=price, volume=vol,
            bid=price-sp/2, ask=price+sp/2, timestamp=max(int(ts/1000),1))
        s = max(0, i-hs)
        ph = [candles[j][4] for j in range(s, i+1)]
        vh = [candles[j][6] for j in range(s, i+1)]
        oih = []
        for j in range(s, i+1):
            b = candles[j][0]//(30*60*1000)*(30*60*1000)
            v = oi_map.get(b, 0)
            if v > 0: oih.append(v)
        if not oih: oih = [0.0]
        bundles.append(MarketDataBundle(market=snap, price_history=ph, volume_history=vh,
            oi_history=oih, funding_history=[0.0],
            liquidation_above=price*1.02, liquidation_below=price*0.98))
    return bundles

def run_flip(bundles, symbol, has_oi=True):
    from app.analytics.feature_engine import FeatureEngine
    from app.backtest.engine import BacktestResult, BacktestTrade, FEE_RATE
    from app.models.enums import Direction

    if has_oi:
        from app.strategy.breakout import BreakoutStrategy
        strategy = BreakoutStrategy(symbol=symbol)
    else:
        from app.strategy.breakout_nooi import BreakoutNoOIStrategy
        strategy = BreakoutNoOIStrategy(symbol=symbol, volume_min=2.0, cooldown_bars=80)

    fe = FeatureEngine()
    equity = 10_000.0
    margin_pct, leverage, trail_atr = 0.25, 25, 2.5
    result = BacktestResult(initial_equity=equity)
    result.equity_curve.append(equity)
    pos = None

    for idx, bundle in enumerate(bundles):
        price = bundle.market.price
        features = fe.build_features(bundle)
        if pos is not None:
            atr = pos["atr"]
            if trail_atr > 0 and atr > 0:
                if pos["dir"] == Direction.LONG:
                    pos["peak"] = max(pos["peak"], price)
                    ns = pos["peak"] - trail_atr * atr
                    if ns > pos["sl"]: pos["sl"] = ns
                else:
                    pos["peak"] = min(pos["peak"], price)
                    ns = pos["peak"] + trail_atr * atr
                    if ns < pos["sl"]: pos["sl"] = ns
            hit = ((pos["dir"] == Direction.LONG and price <= pos["sl"]) or
                   (pos["dir"] == Direction.SHORT and price >= pos["sl"]))
            if hit:
                pnl = (price-pos["ep"])*pos["qty"] if pos["dir"]==Direction.LONG else (pos["ep"]-price)*pos["qty"]
                fee = price * pos["qty"] * FEE_RATE
                equity += pnl - fee
                result.trades.append(BacktestTrade(entry_price=pos["ep"], exit_price=price,
                    direction=pos["dir"], quantity=pos["qty"], pnl=pnl, fee=fee,
                    entry_idx=pos["ei"], exit_idx=idx))
                result.sl_hits += 1; pos = None

        signal = strategy.generate_signal(features)
        if signal is not None:
            if pos is not None and pos["dir"] != signal.direction:
                pnl = (price-pos["ep"])*pos["qty"] if pos["dir"]==Direction.LONG else (pos["ep"]-price)*pos["qty"]
                fee = price * pos["qty"] * FEE_RATE
                equity += pnl - fee
                result.trades.append(BacktestTrade(entry_price=pos["ep"], exit_price=price,
                    direction=pos["dir"], quantity=pos["qty"], pnl=pnl, fee=fee,
                    entry_idx=pos["ei"], exit_idx=idx))
                pos = None
            if pos is None:
                atr = features.atr if features.atr > 0 else price * 0.01
                margin = equity * margin_pct
                qty = margin * leverage / price
                ef = price * qty * FEE_RATE; equity -= ef
                sl = price - atr if signal.direction==Direction.LONG else price + atr
                pos = {"dir": signal.direction, "ep": price, "qty": qty, "sl": sl,
                       "atr": atr, "peak": price, "ei": idx}
        result.equity_curve.append(equity)

    if pos is not None:
        price = bundles[-1].market.price
        pnl = (price-pos["ep"])*pos["qty"] if pos["dir"]==Direction.LONG else (pos["ep"]-price)*pos["qty"]
        fee = price * pos["qty"] * FEE_RATE; equity += pnl - fee
        result.trades.append(BacktestTrade(entry_price=pos["ep"], exit_price=price,
            direction=pos["dir"], quantity=pos["qty"], pnl=pnl, fee=fee,
            entry_idx=pos["ei"], exit_idx=len(bundles)-1))
        result.timeout_exits += 1; result.equity_curve[-1] = equity
    return result

# ============ MAIN ============

def main():
    print(f"{'='*120}")
    print(f"BREAKOUT+FLIP | MEXC + COINGLASS OI")
    print(f"Candles: MEXC | OI: Coinglass V4 (Binance) | Strategy: Breakout+Flip")
    print(f"Margin: 25% | Leverage: 25x | Trailing: 2.5 ATR | 30m")
    print(f"{'='*120}")

    # First get supported coins from Coinglass
    print("\nCoinglass supported coins...", end=" ", flush=True)
    cg_coins = set()
    try:
        data = cg_get("/api/futures/supported-coins")
        if data.get("code") == "0":
            cg_coins = set(data.get("data", []))
            print(f"{len(cg_coins)} coins", flush=True)
    except Exception as e:
        print(f"Error: {e}")

    results = {}
    class_results = {}

    for name, (mexc_sym, cls) in SYMBOLS.items():
        label = f"{name} ({cls})"
        has_oi = name in cg_coins

        print(f"\n[{label}] MEXC {mexc_sym}...", end=" ", flush=True)
        candles = dl_mexc_candles(mexc_sym, "Min30", 1500)
        print(f"{len(candles)}c", end="", flush=True)
        if len(candles) < 100:
            print(" SKIP (<100)")
            continue

        oi = []
        if has_oi:
            print(f" CG-OI...", end="", flush=True)
            oi = dl_coinglass_oi(name, "30min", 500)
            print(f"{len(oi)}", end="", flush=True)
            if len(oi) < 5:
                has_oi = False
                print(f"(weak)", end="", flush=True)

        bundles = build_bundles(candles, oi, f"{name}/USDT:USDT")
        print(f" {len(bundles)}b", end="", flush=True)

        r = run_flip(bundles, f"{name}/USDT:USDT", has_oi=has_oi)
        results[label] = r
        if cls not in class_results: class_results[cls] = []
        class_results[cls].append((name, r))

        pf = f"{r.profit_factor:.2f}" if r.profit_factor < 100 else "inf"
        tag = "CG-OI" if has_oi else "noOI"
        print(f" -> {r.total_trades}tr WR={r.win_rate:.0%} PF={pf} Ret={r.total_return_pct:+.2f}% [{tag}]")

    if not results:
        print("No results!"); return

    # =================== SUMMARY ===================
    print(f"\n{'='*120}")
    print(f"{'Asset':<22} {'Class':<8} {'Tr':>4} {'WR':>5} {'PF':>7} {'Return':>9} {'MDD':>7} {'Equity':>11}")
    print(f"{'-'*120}")
    total_ret, profitable = 0, 0
    for n in sorted(results, key=lambda x: results[x].total_return_pct, reverse=True):
        r = results[n]
        c = n.split("(")[1].rstrip(")") if "(" in n else "?"
        pf = f"{r.profit_factor:.2f}" if r.profit_factor < 100 else "inf"
        print(f"{n:<22} {c:<8} {r.total_trades:>4} {r.win_rate:>4.0%} {pf:>7} {r.total_return_pct:>+8.2f}% {r.max_drawdown_pct:>6.2f}% ${r.final_equity:>10.2f}")
        total_ret += r.total_return_pct
        if r.total_return_pct > 0: profitable += 1
    avg = total_ret / len(results) if results else 0
    print(f"{'-'*120}")
    print(f"{'TOTAL AVG':<22} {'':>8} {'':>4} {'':>5} {'':>7} {avg:>+8.2f}%")
    print(f"{'='*120}")
    print(f"Profitable: {profitable}/{len(results)}")

    # By class
    print(f"\nПо классам:")
    for cls in sorted(class_results):
        rets = [r.total_return_pct for _, r in class_results[cls]]
        avg_c = sum(rets) / len(rets)
        prof = sum(1 for ret in rets if ret > 0)
        print(f"  {cls:<10}: avg {avg_c:+.2f}%, profitable {prof}/{len(rets)}")

    # Top 10 profit
    dep = 10_000.0
    print(f"\nТОП-10 ПРОФИТ НА ${dep:,.0f}:")
    sorted_results = sorted(results.items(), key=lambda x: x[1].total_return_pct, reverse=True)
    for n, r in sorted_results[:10]:
        p = dep * r.total_return_pct / 100
        print(f"  {n:<22} {r.total_return_pct:>+8.2f}% -> {'+'if p>=0 else ''}{p:>8.2f}")
    if len(sorted_results) > 10:
        print(f"  ... ещё {len(sorted_results)-10} активов")
    print(f"  {'─'*60}")
    print(f"  {'СРЕДНИЙ':<22} {avg:>+8.2f}% -> {'+'if avg>=0 else ''}{dep*avg/100:.2f}")

    best = max(results.items(), key=lambda x: x[1].total_return_pct)
    worst = min(results.items(), key=lambda x: x[1].total_return_pct)
    print(f"\n  Best:  {best[0]} ({best[1].total_return_pct:+.2f}%)")
    print(f"  Worst: {worst[0]} ({worst[1].total_return_pct:+.2f}%)")

    # Trade details for top 5
    print(f"\nДетали ТОП-5:")
    for n, r in sorted_results[:5]:
        print(f"  {n}: {r.total_trades}tr WR={r.win_rate:.0%}")
        for j, t in enumerate(r.trades):
            bars = t.exit_idx - t.entry_idx
            hours = bars * 30 / 60
            pnl_s = "+" if t.pnl > 0 else ""
            dur = f"{hours/24:.1f}д" if hours >= 24 else f"{hours:.1f}ч"
            print(f"    #{j+1} {t.direction.value:>5} {t.entry_price:.2f}->{t.exit_price:.2f} PnL={pnl_s}{t.pnl:.2f} {dur}")

if __name__ == "__main__":
    main()
