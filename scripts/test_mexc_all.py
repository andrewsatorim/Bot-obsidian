"""Breakout+Flip on MEXC — ALL asset classes.

Crypto Top-10 + Gold + Silver + Metals + Oil + Stocks Top-10.
Uses MEXC Futures API (contract.mexc.com).

Usage:
    python scripts/test_mexc_all.py
"""
from __future__ import annotations
import os, sys, time, json
import requests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MEXC_BASE = "https://contract.mexc.com"

# ======================= ALL PAIRS =======================
SYMBOLS = {
    # --- CRYPTO TOP-10 ---
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
    # --- GOLD / SILVER ---
    "GOLD": ("XAUUSD_USDT", "Gold"),
    "SILVER": ("XAGUSD_USDT", "Silver"),
    # --- METALS ---
    "COPPER": ("COPPER_USDT", "Metal"),
    "PLATINUM": ("PLATINUM_USDT", "Metal"),
    "PALLADIUM": ("PALLADIUM_USDT", "Metal"),
    "ALUMINUM": ("ALUMINUM_USDT", "Metal"),
    "ZINC": ("ZINC_USDT", "Metal"),
    "NICKEL": ("NICKEL_USDT", "Metal"),
    "TIN": ("TIN_USDT", "Metal"),
    "LEAD": ("LEAD_USDT", "Metal"),
    "STEEL": ("STEEL_USDT", "Metal"),
    "IRON": ("IRON_USDT", "Metal"),
    # --- OIL ---
    "CRUDE": ("CRUDEOIL_USDT", "Oil"),
    "WTI": ("WTI_USDT", "Oil"),
    "BRENT": ("BRENT_USDT", "Oil"),
    # --- STOCKS TOP-10 ---
    "TSLA": ("TSLA_USDT", "Stock"),
    "NVDA": ("NVDA_USDT", "Stock"),
    "AAPL": ("AAPL_USDT", "Stock"),
    "AMZN": ("AMZN_USDT", "Stock"),
    "GOOGL": ("GOOGL_USDT", "Stock"),
    "MSFT": ("MSFT_USDT", "Stock"),
    "META": ("META_USDT", "Stock"),
    "COIN": ("COIN_USDT", "Stock"),
    "MSTR": ("MSTR_USDT", "Stock"),
    "AMD": ("AMD_USDT", "Stock"),
}

def mexc_get(path, params=None):
    resp = requests.get(f"{MEXC_BASE}{path}", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()

def discover_symbols():
    """Find which symbols actually exist on MEXC futures."""
    print("Discovering MEXC futures symbols...", flush=True)
    try:
        data = mexc_get("/api/v1/contract/detail")
        available = {}
        if "data" in data:
            for item in data["data"]:
                sym = item.get("symbol", "")
                available[sym] = item
        return available
    except Exception as e:
        print(f"  Error fetching contract list: {e}")
        return {}

def download_candles_mexc(symbol, interval="Min30", limit=1500):
    """Download kline data from MEXC futures."""
    all_c = []
    # MEXC uses start/end timestamps in seconds
    end = int(time.time())
    while len(all_c) < limit:
        try:
            data = mexc_get(f"/api/v1/contract/kline/{symbol}", {
                "interval": interval,
                "start": end - 300 * 1800,  # go back 300 bars * 30min
                "end": end,
            })
        except Exception as e:
            # Try alternative endpoint
            try:
                data = mexc_get(f"/api/v1/contract/kline/{symbol}", {
                    "interval": interval,
                    "limit": 300,
                })
            except:
                break

        if not data.get("data") or not data["data"].get("time"):
            break

        times = data["data"]["time"]
        opens = data["data"]["open"]
        highs = data["data"]["high"]
        lows = data["data"]["low"]
        closes = data["data"]["close"]
        vols = data["data"]["vol"]

        if not times:
            break

        batch = []
        for i in range(len(times)):
            ts = int(times[i]) * 1000 if times[i] < 1e12 else int(times[i])
            batch.append([
                ts,
                float(opens[i]),
                float(highs[i]),
                float(lows[i]),
                float(closes[i]),
                float(vols[i]),
                float(vols[i]),  # vol as quote vol too
            ])

        if not batch:
            break

        before_len = len(all_c)
        all_c.extend(batch)

        # Remove dupes
        seen = set()
        all_c = [c for c in all_c if c[0] not in seen and not seen.add(c[0])]

        if len(all_c) == before_len:
            break  # No new data

        end = min(c[0] for c in batch) // 1000 - 1
        time.sleep(0.3)

    all_c.sort(key=lambda c: c[0])
    return all_c

def build_bundles(candles, symbol):
    from app.models.market_data_bundle import MarketDataBundle
    from app.models.market_snapshot import MarketSnapshot
    hs = 50
    bundles = []
    for i in range(hs, len(candles)):
        c = candles[i]
        ts, price, vol = c[0], c[4], c[6]
        spread = price * 0.0003
        snap = MarketSnapshot(symbol=symbol, price=price, volume=vol,
            bid=price-spread/2, ask=price+spread/2, timestamp=max(int(ts/1000),1))
        s = max(0, i-hs)
        ph = [candles[j][4] for j in range(s, i+1)]
        vh = [candles[j][6] for j in range(s, i+1)]
        # Approximate OI from volume trend
        oih = [candles[j][5] for j in range(s, i+1)]
        if not oih or max(oih) == 0: oih = [0.0]
        bundles.append(MarketDataBundle(market=snap, price_history=ph, volume_history=vh,
            oi_history=oih, funding_history=[0.0],
            liquidation_above=price*1.02, liquidation_below=price*0.98))
    return bundles

def run_backtest_flip(bundles, symbol):
    """Breakout + Flip backtest."""
    from app.analytics.feature_engine import FeatureEngine
    from app.backtest.engine import BacktestResult, BacktestTrade, FEE_RATE
    from app.models.enums import Direction
    from app.strategy.breakout import BreakoutStrategy

    fe = FeatureEngine()
    strategy = BreakoutStrategy(symbol=symbol)
    equity = 10_000.0
    margin_pct, leverage, atr_mult, trail_atr = 0.25, 25, 1.0, 2.5

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
                pnl = (price - pos["ep"]) * pos["qty"] if pos["dir"] == Direction.LONG else (pos["ep"] - price) * pos["qty"]
                fee = price * pos["qty"] * FEE_RATE
                equity += pnl - fee
                result.trades.append(BacktestTrade(entry_price=pos["ep"], exit_price=price,
                    direction=pos["dir"], quantity=pos["qty"], pnl=pnl, fee=fee,
                    entry_idx=pos["ei"], exit_idx=idx))
                result.sl_hits += 1
                pos = None

        signal = strategy.generate_signal(features)
        if signal is not None:
            if pos is not None and pos["dir"] != signal.direction:
                pnl = (price - pos["ep"]) * pos["qty"] if pos["dir"] == Direction.LONG else (pos["ep"] - price) * pos["qty"]
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
                ef = price * qty * FEE_RATE
                equity -= ef
                sl = price - atr * atr_mult if signal.direction == Direction.LONG else price + atr * atr_mult
                pos = {"dir": signal.direction, "ep": price, "qty": qty, "sl": sl,
                       "atr": atr, "peak": price, "ei": idx}

        result.equity_curve.append(equity)

    if pos is not None:
        price = bundles[-1].market.price
        pnl = (price - pos["ep"]) * pos["qty"] if pos["dir"] == Direction.LONG else (pos["ep"] - price) * pos["qty"]
        fee = price * pos["qty"] * FEE_RATE
        equity += pnl - fee
        result.trades.append(BacktestTrade(entry_price=pos["ep"], exit_price=price,
            direction=pos["dir"], quantity=pos["qty"], pnl=pnl, fee=fee,
            entry_idx=pos["ei"], exit_idx=len(bundles)-1))
        result.timeout_exits += 1
        result.equity_curve[-1] = equity

    return result

def main():
    print(f"{'='*120}")
    print(f"BREAKOUT + FLIP на MEXC | ВСЕ КЛАССЫ АКТИВОВ")
    print(f"Crypto Top-10 + Gold + Silver + Metals + Oil + Stocks Top-10")
    print(f"Margin: 25% | Leverage: 25x | Trailing: 2.5 ATR | 30m")
    print(f"{'='*120}")

    # Discover available symbols
    available = discover_symbols()
    if not available:
        print("Не удалось получить список инструментов MEXC")
        print("Попробуем напрямую по известным символам...")

    valid = []
    for name, (mexc_sym, cls) in SYMBOLS.items():
        if available:
            if mexc_sym in available:
                valid.append((name, mexc_sym, cls))
                print(f"  {name} ({mexc_sym}) - OK", flush=True)
            else:
                # Try variations
                found = False
                for alt in [mexc_sym, mexc_sym.replace("_", ""), name + "_USDT"]:
                    if alt in available:
                        valid.append((name, alt, cls))
                        print(f"  {name} ({alt}) - OK", flush=True)
                        found = True
                        break
                if not found:
                    print(f"  {name} ({mexc_sym}) - N/A", flush=True)
        else:
            valid.append((name, mexc_sym, cls))

    print(f"\n{len(valid)} instruments to test\n")

    results = {}
    by_class = {}

    for name, mexc_sym, cls in valid:
        label = f"{name} ({cls})"
        print(f"[{label}] Downloading {mexc_sym}...", end=" ", flush=True)
        candles = download_candles_mexc(mexc_sym, "Min30", 1500)
        print(f"{len(candles)}c", end="", flush=True)

        if len(candles) < 100:
            print(f" SKIP (<100 candles)")
            continue

        bundles = build_bundles(candles, f"{name}/USDT:USDT")
        print(f" {len(bundles)}b", end="", flush=True)

        if not bundles:
            print(" SKIP")
            continue

        r = run_backtest_flip(bundles, f"{name}/USDT:USDT")
        results[label] = r
        if cls not in by_class: by_class[cls] = []
        by_class[cls].append((name, r))
        pf = f"{r.profit_factor:.2f}" if r.profit_factor < 100 else "inf"
        print(f" -> {r.total_trades}tr WR={r.win_rate:.0%} PF={pf} Ret={r.total_return_pct:+.2f}%")

    if not results:
        print("\nНет результатов!")
        return

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
    print(f"\nProfitable: {profitable}/{len(results)}")

    # By class
    print(f"\nПо классам активов:")
    for cls in sorted(by_class):
        rets = [r.total_return_pct for _, r in by_class[cls]]
        avg_c = sum(rets) / len(rets)
        prof = sum(1 for ret in rets if ret > 0)
        print(f"  {cls:<10}: avg {avg_c:+.2f}%, profitable {prof}/{len(rets)}")

    # Profit on $10K
    dep = 10_000.0
    print(f"\nПРОФИТ НА ${dep:,.0f}:")
    for n in sorted(results, key=lambda x: results[x].total_return_pct, reverse=True):
        r = results[n]
        p = dep * r.total_return_pct / 100
        print(f"  {n:<22} {r.total_return_pct:>+8.2f}% -> {'+'if p>=0 else ''}{p:>8.2f}")
    print(f"  {'─'*60}")
    print(f"  {'СРЕДНИЙ':<22} {avg:>+8.2f}% -> +{dep*avg/100:.2f}")

    # Best/worst
    if results:
        best = max(results.items(), key=lambda x: x[1].total_return_pct)
        worst = min(results.items(), key=lambda x: x[1].total_return_pct)
        print(f"\n  Best:  {best[0]} ({best[1].total_return_pct:+.2f}%)")
        print(f"  Worst: {worst[0]} ({worst[1].total_return_pct:+.2f}%)")

if __name__ == "__main__":
    main()
