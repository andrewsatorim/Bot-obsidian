"""Compare ALL strategies on same data — find the best one.

Tests: Breakout, CandleVolume, Swing, Donchian on 30m + 4H.

Usage:
    python scripts/test_compare_all.py
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

def run_strategy(bundles, strategy, symbol):
    from app.analytics.feature_engine import FeatureEngine
    from app.backtest.engine import BacktestEngine, TPLevel
    from app.config import Settings
    from app.risk.risk_manager import RiskManager
    settings = Settings(account_equity=10_000.0, paper_trading=True, max_position_pct=0.15)

    # Different configs per strategy type
    strategy_name = type(strategy).__name__

    if strategy_name == "BreakoutStrategy":
        tp_levels = [
            TPLevel(0.08, 0.40, True),
            TPLevel(0.25, 0.35, False),
            TPLevel(0.60, 1.0, False),
        ]
        engine = BacktestEngine(
            analytics=FeatureEngine(), strategy=strategy, risk=RiskManager(settings),
            initial_equity=10_000.0, leverage=25, max_position_pct=0.15,
            atr_risk_multiplier=1.0, tp_levels=tp_levels, trailing_stop_atr=0.0,
        )
    elif strategy_name == "CandleVolumeStrategy":
        # Candle patterns with trailing stop
        tp_levels = [
            TPLevel(0.10, 0.50, True),   # Take 50% at +10% on margin
            TPLevel(0.40, 1.0, False),    # Close rest at +40%
        ]
        engine = BacktestEngine(
            analytics=FeatureEngine(), strategy=strategy, risk=RiskManager(settings),
            initial_equity=10_000.0, leverage=25, max_position_pct=0.15,
            atr_risk_multiplier=1.5, tp_levels=tp_levels, trailing_stop_atr=2.5,
        )
    else:
        # Default: trailing stop only
        engine = BacktestEngine(
            analytics=FeatureEngine(), strategy=strategy, risk=RiskManager(settings),
            initial_equity=10_000.0, leverage=25, max_position_pct=0.15,
            atr_risk_multiplier=2.0, tp_levels=[], trailing_stop_atr=3.0,
        )

    return engine.run(bundles)

def main():
    from app.strategy.breakout import BreakoutStrategy
    from app.strategy.candle_volume import CandleVolumeStrategy

    print(f"{'='*100}")
    print(f"СРАВНЕНИЕ СТРАТЕГИЙ НА ОДНИХ ДАННЫХ")
    print(f"BTC + ETH + SOL | 30m | 1 месяц | Leverage 25x | Margin 15%")
    print(f"{'='*100}")

    strategies_config = [
        ("Breakout", lambda sym: BreakoutStrategy(symbol=sym)),
        ("CandleVol", lambda sym: CandleVolumeStrategy(symbol=sym, min_score=3, cooldown_bars=15)),
        ("CandleVol-2", lambda sym: CandleVolumeStrategy(symbol=sym, min_score=2, cooldown_bars=20)),
    ]

    all_results = {}  # {strategy_name: {symbol: result}}

    for okx_id, ccxt_id in SYMBOLS:
        short = ccxt_id.split("/")[0]
        print(f"\n[{short}] Downloading...", end=" ", flush=True)
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

        for strat_name, strat_factory in strategies_config:
            strategy = strat_factory(ccxt_id)
            r = run_strategy(bundles, strategy, ccxt_id)
            if strat_name not in all_results:
                all_results[strat_name] = {}
            all_results[strat_name][short] = r
            pf = f"{r.profit_factor:.2f}" if r.profit_factor < 100 else "inf"
            print(f"  {strat_name:<12} {r.total_trades:>3}tr WR={r.win_rate:.0%} PF={pf:>5} Ret={r.total_return_pct:>+7.2f}%")

    # Summary table
    print(f"\n{'='*100}")
    print(f"{'Стратегия':<14}", end="")
    for okx_id, ccxt_id in SYMBOLS:
        short = ccxt_id.split("/")[0]
        print(f" {short:>10}", end="")
    print(f" {'СРЕДНИЙ':>10}")
    print(f"{'-'*100}")

    best_strat = None
    best_avg = -999

    for strat_name in all_results:
        print(f"{strat_name:<14}", end="")
        rets = []
        for okx_id, ccxt_id in SYMBOLS:
            short = ccxt_id.split("/")[0]
            if short in all_results[strat_name]:
                r = all_results[strat_name][short]
                print(f" {r.total_return_pct:>+9.2f}%", end="")
                rets.append(r.total_return_pct)
            else:
                print(f" {'N/A':>10}", end="")
        avg = sum(rets) / len(rets) if rets else 0
        print(f" {avg:>+9.2f}%")
        if avg > best_avg:
            best_avg = avg
            best_strat = strat_name

    print(f"{'='*100}")
    print(f"\nЛучшая стратегия: {best_strat} (avg {best_avg:+.2f}%)")

    # Trade details for best
    if best_strat and best_strat in all_results:
        print(f"\nДетали {best_strat}:")
        for short, r in all_results[best_strat].items():
            print(f"  {short}: {r.total_trades}tr WR={r.win_rate:.0%} SL={r.sl_hits} Timeout={r.timeout_exits}")
            for j, t in enumerate(r.trades):
                bars = t.exit_idx - t.entry_idx
                hours = bars * 30 / 60
                pnl_sign = "+" if t.pnl > 0 else ""
                print(f"    #{j+1} {t.direction.value:>5} {t.entry_price:.2f}->{t.exit_price:.2f} "
                      f"PnL={pnl_sign}{t.pnl:.2f} {hours:.1f}ч")

    # Profit on $10K
    deposit = 10_000.0
    print(f"\nПрофит на ${deposit:,.0f}:")
    for strat_name in all_results:
        rets = [all_results[strat_name][s].total_return_pct
                for s in all_results[strat_name]]
        avg = sum(rets) / len(rets) if rets else 0
        profit = deposit * avg / 100
        print(f"  {strat_name:<14} {avg:>+7.2f}% -> {'+' if profit >= 0 else ''}{profit:.2f}")

if __name__ == "__main__":
    main()
