"""Breakout + Position Flip — flip position on reverse signal.

When in SHORT and get LONG signal → close SHORT, open LONG immediately.
This catches both sides of trend changes without waiting.

Usage:
    python scripts/test_breakout_flip.py
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
    r = requests.get(f"{BASE_URL}{path}", params=params, timeout=15)
    r.raise_for_status()
    return r.json()

def check_inst(inst_id):
    try:
        d = okx_get("/api/v5/public/instruments", {"instType": "SWAP", "instId": inst_id})
        return len(d.get("data", [])) > 0
    except: return False

def dl_candles(inst_id, bar="30m", limit=1500):
    all_c, after = [], ""
    while len(all_c) < limit:
        p = {"instId": inst_id, "bar": bar, "limit": "300"}
        if after: p["after"] = after
        try: d = okx_get("/api/v5/market/candles", p)
        except: break
        c = d.get("data", [])
        if not c: break
        for x in c:
            all_c.append([int(x[0]),float(x[1]),float(x[2]),float(x[3]),float(x[4]),float(x[5]),float(x[7])])
        after = c[-1][0]; time.sleep(0.2)
    all_c.sort(key=lambda x: x[0])
    seen = set()
    return [c for c in all_c if c[0] not in seen and not seen.add(c[0])]

def dl_oi(inst_id):
    all_oi, after = [], ""
    while len(all_oi) < 500:
        p = {"instId": inst_id, "period": "30m", "limit": "100"}
        if after: p["after"] = after
        try: d = okx_get("/api/v5/rubik/stat/contracts/open-interest-history", p)
        except: break
        recs = d.get("data", [])
        if not recs:
            try:
                d2 = okx_get("/api/v5/public/open-interest", {"instId": inst_id})
                for r in d2.get("data", []):
                    if isinstance(r, dict): all_oi.append({"ts": int(r.get("ts",0)), "oiCcy": float(r.get("oiCcy",0))})
            except: pass
            break
        for r in recs:
            if isinstance(r, dict): all_oi.append({"ts": int(r.get("ts",0)), "oiCcy": float(r.get("oiCcy",0))})
            elif isinstance(r, (list,tuple)) and len(r)>=3: all_oi.append({"ts": int(r[0]), "oiCcy": float(r[2])})
        if not all_oi: break
        after = str(all_oi[-1]["ts"]); time.sleep(0.2)
    all_oi.sort(key=lambda x: x["ts"])
    return all_oi

def dl_funding(inst_id):
    all_r, after = [], ""
    while len(all_r) < 300:
        p = {"instId": inst_id, "limit": "100"}
        if after: p["after"] = after
        try: d = okx_get("/api/v5/public/funding-rate-history", p)
        except: break
        recs = d.get("data", [])
        if not recs: break
        for r in recs:
            if isinstance(r, dict): all_r.append({"ts": int(r.get("fundingTime",0)), "rate": float(r.get("fundingRate",0))})
        if not all_r: break
        after = recs[-1].get("fundingTime","") if isinstance(recs[-1], dict) else ""
        if not after: break
        time.sleep(0.2)
    all_r.sort(key=lambda x: x["ts"])
    return all_r

def build_bundles(candles, oi_hist, funding, symbol):
    from app.models.market_data_bundle import MarketDataBundle
    from app.models.market_snapshot import MarketSnapshot
    oi_map = {r["ts"]//(30*60*1000)*(30*60*1000): r.get("oiCcy",0) for r in oi_hist}
    fm = {}
    for r in funding: fm[r["ts"]//(3600*1000)] = r["rate"]
    sf = sorted(fm.items())
    hs, bundles = 50, []
    for i in range(hs, len(candles)):
        c = candles[i]
        ts, price, vol = c[0], c[4], c[6] if len(c)>6 else c[5]
        sp = price*0.0002
        snap = MarketSnapshot(symbol=symbol, price=price, volume=vol,
            bid=price-sp/2, ask=price+sp/2, timestamp=max(int(ts/1000),1))
        s = max(0,i-hs)
        ph = [candles[j][4] for j in range(s,i+1)]
        vh = [candles[j][6] if len(candles[j])>6 else candles[j][5] for j in range(s,i+1)]
        oih = [oi_map.get(candles[j][0]//(30*60*1000)*(30*60*1000),0) for j in range(s,i+1)]
        oih = [v for v in oih if v>0] or [0.0]
        ch = ts//(3600*1000)
        fh = [r for h,r in sf if h<=ch] or [0.0]
        bundles.append(MarketDataBundle(market=snap, price_history=ph, volume_history=vh,
            oi_history=oih, funding_history=fh, liquidation_above=price*1.02, liquidation_below=price*0.98))
    return bundles

def run_backtest_flip(bundles, symbol):
    """Custom backtest with position flipping."""
    from app.analytics.feature_engine import FeatureEngine
    from app.backtest.engine import BacktestResult, BacktestTrade, FEE_RATE
    from app.models.enums import Direction
    from app.strategy.breakout import BreakoutStrategy

    fe = FeatureEngine()
    strategy = BreakoutStrategy(symbol=symbol)
    equity = 10_000.0
    margin_pct = 0.25
    leverage = 25
    atr_mult = 1.0
    trail_atr = 2.5

    result = BacktestResult(initial_equity=equity)
    result.equity_curve.append(equity)

    pos = None  # {direction, entry_price, qty, sl, atr, peak}

    for idx, bundle in enumerate(bundles):
        price = bundle.market.price
        features = fe.build_features(bundle)

        # Update trailing stop if in position
        if pos is not None:
            atr = pos["atr"]
            if trail_atr > 0 and atr > 0:
                if pos["direction"] == Direction.LONG:
                    pos["peak"] = max(pos["peak"], price)
                    new_sl = pos["peak"] - trail_atr * atr
                    if new_sl > pos["sl"]: pos["sl"] = new_sl
                else:
                    pos["peak"] = min(pos["peak"], price)
                    new_sl = pos["peak"] + trail_atr * atr
                    if new_sl < pos["sl"]: pos["sl"] = new_sl

            # Check SL
            hit_sl = ((pos["direction"] == Direction.LONG and price <= pos["sl"]) or
                      (pos["direction"] == Direction.SHORT and price >= pos["sl"]))
            if hit_sl:
                if pos["direction"] == Direction.LONG:
                    pnl = (price - pos["entry_price"]) * pos["qty"]
                else:
                    pnl = (pos["entry_price"] - price) * pos["qty"]
                fee = price * pos["qty"] * FEE_RATE
                equity += pnl - fee
                result.trades.append(BacktestTrade(
                    entry_price=pos["entry_price"], exit_price=price,
                    direction=pos["direction"], quantity=pos["qty"],
                    pnl=pnl, fee=fee, entry_idx=pos["entry_idx"], exit_idx=idx))
                result.sl_hits += 1
                pos = None

        # Generate signal
        signal = strategy.generate_signal(features)

        if signal is not None:
            # FLIP: if in opposite position, close and open new
            if pos is not None and pos["direction"] != signal.direction:
                if pos["direction"] == Direction.LONG:
                    pnl = (price - pos["entry_price"]) * pos["qty"]
                else:
                    pnl = (pos["entry_price"] - price) * pos["qty"]
                fee = price * pos["qty"] * FEE_RATE
                equity += pnl - fee
                result.trades.append(BacktestTrade(
                    entry_price=pos["entry_price"], exit_price=price,
                    direction=pos["direction"], quantity=pos["qty"],
                    pnl=pnl, fee=fee, entry_idx=pos["entry_idx"], exit_idx=idx))
                pos = None

            # Open new position
            if pos is None:
                atr = features.atr if features.atr > 0 else price * 0.01
                margin = equity * margin_pct
                notional = margin * leverage
                qty = notional / price
                entry_fee = price * qty * FEE_RATE
                equity -= entry_fee
                if signal.direction == Direction.LONG:
                    sl = price - atr * atr_mult
                else:
                    sl = price + atr * atr_mult
                pos = {
                    "direction": signal.direction,
                    "entry_price": price,
                    "qty": qty, "sl": sl, "atr": atr,
                    "peak": price, "entry_idx": idx,
                }

        result.equity_curve.append(equity)

    # Force close
    if pos is not None:
        price = bundles[-1].market.price
        if pos["direction"] == Direction.LONG:
            pnl = (price - pos["entry_price"]) * pos["qty"]
        else:
            pnl = (pos["entry_price"] - price) * pos["qty"]
        fee = price * pos["qty"] * FEE_RATE
        equity += pnl - fee
        result.trades.append(BacktestTrade(
            entry_price=pos["entry_price"], exit_price=price,
            direction=pos["direction"], quantity=pos["qty"],
            pnl=pnl, fee=fee, entry_idx=pos["entry_idx"], exit_idx=len(bundles)-1))
        result.timeout_exits += 1
        result.equity_curve[-1] = equity

    return result

def main():
    print(f"{'='*110}")
    print(f"BREAKOUT + POSITION FLIP")
    print(f"Reverse signal → close current + open opposite immediately")
    print(f"Margin: 25% | Leverage: 25x | SL: 1.0 ATR | Trailing: 2.5 ATR | NO TP")
    print(f"{'='*110}")

    print("\nChecking...", end=" ", flush=True)
    valid = []
    for oid, cid, cls in SYMBOLS:
        if check_inst(oid):
            valid.append((oid, cid, cls))
            print(oid.split("-")[0], end=" ", flush=True)
        time.sleep(0.2)
    print(f"\n{len(valid)} available\n")

    results = {}
    for oid, cid, cls in valid:
        short = cid.split("/")[0]
        label = f"{short} ({cls})"
        print(f"[{label}] Downloading...", end=" ", flush=True)
        candles = dl_candles(oid)
        print(f"{len(candles)}c", end="", flush=True)
        if len(candles) < 100: print(" SKIP"); continue
        oi = dl_oi(oid)
        print(f" {len(oi)}oi", end="", flush=True)
        funding = dl_funding(oid)
        print(f" {len(funding)}f", end="", flush=True)
        bundles = build_bundles(candles, oi, funding, cid)
        print(f" {len(bundles)}b", end="", flush=True)
        if not bundles: print(" SKIP"); continue
        r = run_backtest_flip(bundles, cid)
        results[label] = r
        pf = f"{r.profit_factor:.2f}" if r.profit_factor < 100 else "inf"
        print(f" -> {r.total_trades}tr WR={r.win_rate:.0%} PF={pf} Ret={r.total_return_pct:+.2f}%")

    print(f"\n{'='*110}")
    print(f"{'Asset':<20} {'Cls':<6} {'Tr':>4} {'WR':>5} {'PF':>6} {'Return':>8} {'MDD':>7} {'Equity':>10}")
    print(f"{'-'*110}")
    total_ret, profitable = 0, 0
    for n in sorted(results, key=lambda x: results[x].total_return_pct, reverse=True):
        r = results[n]
        c = n.split("(")[1].rstrip(")") if "(" in n else "?"
        pf = f"{r.profit_factor:.2f}" if r.profit_factor < 100 else "inf"
        print(f"{n:<20} {c:<6} {r.total_trades:>4} {r.win_rate:>4.0%} {pf:>6} {r.total_return_pct:>+7.2f}% {r.max_drawdown_pct:>6.2f}% ${r.final_equity:>9.2f}")
        total_ret += r.total_return_pct
        if r.total_return_pct > 0: profitable += 1
    avg = total_ret / len(results) if results else 0
    print(f"{'-'*110}")
    print(f"{'AVG':<20} {'':>6} {'':>4} {'':>5} {'':>6} {avg:>+7.2f}%")
    print(f"{'='*110}")

    if results:
        print(f"\nProfitable: {profitable}/{len(results)}")
        print(f"\nСДЕЛКИ:")
        for n in sorted(results, key=lambda x: results[x].total_return_pct, reverse=True):
            r = results[n]
            if not r.trades: print(f"  {n}: нет сделок"); continue
            print(f"  {n}:")
            for j, t in enumerate(r.trades):
                bars = t.exit_idx - t.entry_idx
                hours = bars * 30 / 60
                pnl_s = "+" if t.pnl > 0 else ""
                dur = f"{hours/24:.1f}д" if hours >= 24 else f"{hours:.1f}ч"
                print(f"    #{j+1} {t.direction.value:>5} {t.entry_price:.2f}->{t.exit_price:.2f} PnL={pnl_s}{t.pnl:.2f} {dur}")

        dep = 10_000.0
        print(f"\nПРОФИТ НА ${dep:,.0f}:")
        for n in sorted(results, key=lambda x: results[x].total_return_pct, reverse=True):
            r = results[n]
            p = dep * r.total_return_pct / 100
            print(f"  {n:<20} {r.total_return_pct:>+7.2f}% -> {'+'if p>=0 else ''}{p:.2f}")
        print(f"  {'СРЕДНИЙ':<20} {avg:>+7.2f}% -> +{dep*avg/100:.2f}")

if __name__ == "__main__":
    main()
