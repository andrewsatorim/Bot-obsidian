"""Breakout+Flip on MEXC — AUTO-DISCOVER ALL pairs.

Auto-discovers ALL futures on MEXC via API.
Uses OKX OI data for crypto pairs (variant 3).
NoOI for stocks/indices/commodities.

Usage:
    python scripts/test_mexc_full.py
"""
from __future__ import annotations
import os, sys, time
import requests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MEXC_BASE = "https://contract.mexc.com"
OKX_BASE = "https://www.okx.com"

def mexc_get(path, params=None):
    r = requests.get(f"{MEXC_BASE}{path}", params=params, timeout=15)
    r.raise_for_status()
    return r.json()

def okx_get(path, params=None):
    r = requests.get(f"{OKX_BASE}{path}", params=params, timeout=15)
    r.raise_for_status()
    return r.json()

# ============ STEP 1: AUTO-DISCOVER ALL MEXC FUTURES ============

def discover_all_mexc():
    """Get ALL futures pairs from MEXC, categorize them."""
    print("Discovering ALL MEXC futures...", flush=True)
    try:
        data = mexc_get("/api/v1/contract/detail")
    except Exception as e:
        print(f"  Error: {e}")
        return {}

    symbols = {}
    for item in data.get("data", []):
        sym = item.get("symbol", "")
        if not sym or "_USDT" not in sym:
            continue

        base = sym.replace("_USDT", "")

        # Classify
        crypto = {"BTC","ETH","SOL","XRP","DOGE","ADA","AVAX","LINK","DOT","SUI",
                   "PEPE","SHIB","MATIC","ARB","OP","APT","SEI","TIA","WLD","JUP",
                   "NEAR","ATOM","FIL","ICP","INJ","FET","RENDER","TAO","ONDO","PYTH",
                   "TON","TRX","LTC","BCH","ETC","XLM","ALGO","VET","HBAR","FTM",
                   "SAND","MANA","AXS","GALA","IMX","BLUR","WIF","BONK","FLOKI","MEW",
                   "PIPPIN","PENGU","TRUMP","PIPPINUSDT","1000PEPE","1000BONK","1000FLOKI",
                   "1000SHIB","1000SATS","ORDI","STX","RUNE","KAS","NOT","BRETT","POPCAT"}
        indices = {"SP500","NAS100","US30","US500","NASDAQ","DJ30"}
        metals = {"XAUT","GOLD","SILVER","COPPER","PLATINUM","PALLADIUM","ALUMINUM",
                  "ZINC","NICKEL","TIN","LEAD","STEEL","IRON","XAU","XAG"}
        oil = {"USOIL","UKOIL","WTI","BRENT","CRUDEOIL","NGAS","NATURALGAS"}
        stocks = {"TSLA","NVDA","AAPL","AMZN","GOOGL","MSFT","META","COIN","MSTR",
                  "AMD","MU","CSCO","MRVL","UNH","HOOD","RDDT","LIN","INTC","NFLX",
                  "DIS","BA","GS","JPM","V","MA","PYPL","SQ","SHOP","PLTR","SNOW",
                  "CRM","ORCL","UBER","ABNB","RIVN","LCID","NIO","BABA","JD","PDD",
                  "TESLA","APPLE","NVIDIA","AMAZON","MICROSOFT"}

        if base in crypto or base.replace("1000","") in crypto:
            cls = "Crypto"
        elif base in indices:
            cls = "Index"
        elif base in metals:
            cls = "Metal"
        elif base in oil:
            cls = "Oil"
        elif base in stocks:
            cls = "Stock"
        else:
            # Try to detect by display name or just skip unknowns
            display = item.get("displayName", "").upper()
            if any(s in display for s in ["INDEX","S&P","NASDAQ","DOW"]):
                cls = "Index"
            elif any(s in display for s in ["OIL","CRUDE","GAS"]):
                cls = "Oil"
            elif any(s in display for s in ["GOLD","SILVER","COPPER","METAL","PLAT"]):
                cls = "Metal"
            else:
                cls = "Crypto"  # default

        symbols[sym] = {"base": base, "class": cls, "symbol": sym}

    return symbols

# ============ STEP 2: DOWNLOAD DATA ============

def dl_mexc_candles(symbol, interval="Min30", limit=1500):
    all_c = []
    end = int(time.time())
    for _ in range(10):  # max 10 pages
        try:
            data = mexc_get(f"/api/v1/contract/kline/{symbol}", {
                "interval": interval, "start": end - 300 * 1800, "end": end,
            })
        except:
            break
        d = data.get("data", {})
        times = d.get("time", [])
        if not times: break
        opens = d.get("open", []); highs = d.get("high", [])
        lows = d.get("low", []); closes = d.get("close", []); vols = d.get("vol", [])
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

def dl_okx_oi(base_symbol):
    """Download OI from OKX for crypto symbols."""
    inst_id = f"{base_symbol}-USDT-SWAP"
    all_oi, after = [], ""
    while len(all_oi) < 500:
        params = {"instId": inst_id, "period": "30m", "limit": "100"}
        if after: params["after"] = after
        try:
            data = okx_get("/api/v5/rubik/stat/contracts/open-interest-history", params)
        except: break
        recs = data.get("data", [])
        if not recs:
            try:
                d2 = okx_get("/api/v5/public/open-interest", {"instId": inst_id})
                for r in d2.get("data", []):
                    if isinstance(r, dict):
                        all_oi.append({"ts": int(r.get("ts",0)), "oiCcy": float(r.get("oiCcy",0))})
            except: pass
            break
        for r in recs:
            if isinstance(r, dict):
                all_oi.append({"ts": int(r.get("ts",0)), "oiCcy": float(r.get("oiCcy",0))})
            elif isinstance(r, (list,tuple)) and len(r) >= 3:
                all_oi.append({"ts": int(r[0]), "oiCcy": float(r[2])})
        if not all_oi: break
        after = str(all_oi[-1]["ts"])
        time.sleep(0.2)
    all_oi.sort(key=lambda x: x["ts"])
    return all_oi

# ============ STEP 3: BUILD & BACKTEST ============

def build_bundles(candles, oi_history, symbol):
    from app.models.market_data_bundle import MarketDataBundle
    from app.models.market_snapshot import MarketSnapshot
    oi_map = {}
    for r in oi_history:
        bucket = r["ts"] // (30*60*1000) * (30*60*1000)
        oi_map[bucket] = r.get("oiCcy", 0)
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
                sl = price - atr*atr_mult if signal.direction==Direction.LONG else price + atr*atr_mult
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
    print(f"BREAKOUT+FLIP | MEXC ALL PAIRS | OKX OI for crypto")
    print(f"Auto-discover all MEXC futures + OKX Open Interest")
    print(f"Margin: 25% | Leverage: 25x | Trailing: 2.5 ATR | 30m")
    print(f"{'='*120}")

    # Discover ALL MEXC symbols
    all_mexc = discover_all_mexc()
    if not all_mexc:
        print("Failed to discover MEXC symbols!")
        return

    # Group by class
    by_class = {}
    for sym, info in all_mexc.items():
        cls = info["class"]
        if cls not in by_class: by_class[cls] = []
        by_class[cls].append(info)

    print(f"\nFound {len(all_mexc)} futures on MEXC:")
    for cls in sorted(by_class):
        names = [i["base"] for i in by_class[cls]][:20]
        extra = f" +{len(by_class[cls])-20} more" if len(by_class[cls]) > 20 else ""
        print(f"  {cls:<8}: {len(by_class[cls])} pairs — {', '.join(names)}{extra}")

    # Select TOP pairs per class
    selected = []

    # Crypto: top 10
    crypto_top = ["BTC","ETH","SOL","XRP","DOGE","ADA","AVAX","LINK","DOT","SUI"]
    for sym, info in all_mexc.items():
        if info["base"] in crypto_top and info["class"] == "Crypto":
            selected.append(info)

    # ALL non-crypto (indices, stocks, metals, oil)
    for sym, info in all_mexc.items():
        if info["class"] != "Crypto":
            selected.append(info)

    print(f"\nTesting {len(selected)} pairs...\n")

    results = {}
    class_results = {}

    for info in selected:
        sym = info["symbol"]
        base = info["base"]
        cls = info["class"]
        label = f"{base} ({cls})"

        print(f"[{label}] MEXC...", end=" ", flush=True)
        candles = dl_mexc_candles(sym, "Min30", 1500)
        print(f"{len(candles)}c", end="", flush=True)
        if len(candles) < 100:
            print(" SKIP (<100)")
            continue

        # Get OI from OKX for crypto
        has_oi = False
        oi = []
        if cls == "Crypto":
            print(f" OKX-OI...", end="", flush=True)
            oi = dl_okx_oi(base)
            if len(oi) > 10:
                has_oi = True
                print(f"{len(oi)}oi", end="", flush=True)
            else:
                print(f"0oi", end="", flush=True)

        bundles = build_bundles(candles, oi, f"{base}/USDT:USDT")
        print(f" {len(bundles)}b", end="", flush=True)
        if not bundles:
            print(" SKIP")
            continue

        r = run_flip(bundles, f"{base}/USDT:USDT", has_oi=has_oi)
        results[label] = r
        if cls not in class_results: class_results[cls] = []
        class_results[cls].append((base, r))

        pf = f"{r.profit_factor:.2f}" if r.profit_factor < 100 else "inf"
        oi_tag = "+OI" if has_oi else "noOI"
        print(f" -> {r.total_trades}tr WR={r.win_rate:.0%} PF={pf} Ret={r.total_return_pct:+.2f}% [{oi_tag}]")

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
    print(f"\nProfitable: {profitable}/{len(results)}")

    # By class
    print(f"\nПо классам:")
    for cls in sorted(class_results):
        rets = [r.total_return_pct for _, r in class_results[cls]]
        avg_c = sum(rets) / len(rets)
        prof = sum(1 for ret in rets if ret > 0)
        print(f"  {cls:<10}: avg {avg_c:+.2f}%, profitable {prof}/{len(rets)}")

    # Profit
    dep = 10_000.0
    print(f"\nПРОФИТ НА ${dep:,.0f}:")
    for n in sorted(results, key=lambda x: results[x].total_return_pct, reverse=True)[:10]:
        r = results[n]
        p = dep * r.total_return_pct / 100
        print(f"  {n:<22} {r.total_return_pct:>+8.2f}% -> {'+'if p>=0 else ''}{p:>8.2f}")
    print(f"  ...")
    print(f"  {'СРЕДНИЙ':<22} {avg:>+8.2f}% -> {'+'if avg>=0 else ''}{dep*avg/100:.2f}")

    best = max(results.items(), key=lambda x: x[1].total_return_pct)
    worst = min(results.items(), key=lambda x: x[1].total_return_pct)
    print(f"\n  Best:  {best[0]} ({best[1].total_return_pct:+.2f}%)")
    print(f"  Worst: {worst[0]} ({worst[1].total_return_pct:+.2f}%)")

if __name__ == "__main__":
    main()
