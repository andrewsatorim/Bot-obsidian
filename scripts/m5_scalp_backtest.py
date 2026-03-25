"""M5 Scalping Backtest: Bayesian filters + φ-compressed take-profits.

Config:
  Asset:      BTC/USDT:USDT perp
  Timeframe:  M5 (5-minute candles)
  Leverage:   40x isolated
  Margin:     ≤2% of capital per trade
  Entry:      Only when 3 Bayesian filters pass (RSI + VWAP + Volume)
  Stop-loss:  -0.5% price (= -20% margin) — hard
  Take-profits (5 φ-compressed levels):
    T1: +0.03% price → close 42%
    T2: +0.05% price → close 26%
    T3: +0.08% price → close 16%  → move SL to breakeven
    T4: +0.12% price → close 11%
    T5: +0.18% price → close 5%
  Max trades/day: 20-40
  Circuit breaker: 3 consecutive stops → pause 30min (6 candles on M5)

Usage:
    python scripts/m5_scalp_backtest.py
"""
from __future__ import annotations

import csv
import json
import logging
import math
import os
import sys
import time
from collections import deque
from dataclasses import dataclass, field as datafield
from statistics import mean, pstdev
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════
LEVERAGE = 40
MARGIN_PCT = 0.02          # 2% of capital per trade
SL_PRICE_PCT = 0.005       # -0.5% price = -20% margin
FEE_RATE = 0.001           # 0.1% per side (maker+taker avg)

# φ-compressed take-profit levels (price move %, close %)
TP_LEVELS = [
    (0.0003, 0.42),   # T1: +0.03% → 42%
    (0.0005, 0.26),   # T2: +0.05% → 26%
    (0.0008, 0.16),   # T3: +0.08% → 16% → SL to breakeven
    (0.0012, 0.11),   # T4: +0.12% → 11%
    (0.0018, 0.05),   # T5: +0.18% → 5%
]
BE_AFTER_TP = 2            # Move SL to entry after TP index 2 (T3)

MAX_TRADES_PER_DAY = 40
CONSECUTIVE_STOPS_PAUSE = 3
PAUSE_CANDLES = 6          # 30 min on M5

# Bayesian filter thresholds
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
VWAP_DEVIATION_THRESHOLD = 0.001  # 0.1% from VWAP
VOLUME_SPIKE_RATIO = 1.3          # Volume > 1.3x average


# ═══════════════════════════════════════════════════════════
# BAYESIAN FILTERS
# ═══════════════════════════════════════════════════════════

def compute_rsi(prices: list[float], period: int = RSI_PERIOD) -> float:
    """Compute RSI from price history."""
    if len(prices) < period + 1:
        return 50.0
    changes = [prices[i] - prices[i - 1] for i in range(len(prices) - period, len(prices))]
    gains = [c for c in changes if c > 0]
    losses = [-c for c in changes if c < 0]
    avg_gain = mean(gains) if gains else 0.0
    avg_loss = mean(losses) if losses else 0.0001
    rs = avg_gain / avg_loss if avg_loss > 0 else 100
    return 100 - (100 / (1 + rs))


def compute_vwap(prices: list[float], volumes: list[float]) -> float:
    """Volume-Weighted Average Price."""
    if not prices or not volumes or len(prices) != len(volumes):
        return prices[-1] if prices else 0.0
    total_pv = sum(p * v for p, v in zip(prices, volumes))
    total_v = sum(volumes)
    return total_pv / total_v if total_v > 0 else prices[-1]


def bayesian_filter(
    price: float,
    prices: list[float],
    volumes: list[float],
    current_volume: float,
) -> Optional[str]:
    """Apply 3 Bayesian filters. Returns 'LONG', 'SHORT', or None.

    Filter 1 (RSI): oversold → LONG signal, overbought → SHORT signal
    Filter 2 (VWAP): price below VWAP → LONG, above → SHORT
    Filter 3 (Volume): current volume > 1.3x average → confirms signal

    All 3 must agree on direction for entry.
    """
    if len(prices) < RSI_PERIOD + 1:
        return None

    # Filter 1: RSI
    rsi = compute_rsi(prices)
    if rsi < RSI_OVERSOLD:
        rsi_signal = "LONG"
    elif rsi > RSI_OVERBOUGHT:
        rsi_signal = "SHORT"
    else:
        return None  # RSI neutral — no trade

    # Filter 2: VWAP deviation
    vwap = compute_vwap(prices[-20:], volumes[-20:]) if len(prices) >= 20 else mean(prices[-10:])
    vwap_dev = (price - vwap) / vwap if vwap > 0 else 0
    if vwap_dev < -VWAP_DEVIATION_THRESHOLD:
        vwap_signal = "LONG"   # Price below VWAP
    elif vwap_dev > VWAP_DEVIATION_THRESHOLD:
        vwap_signal = "SHORT"  # Price above VWAP
    else:
        return None  # Near VWAP — no edge

    # Filter 3: Volume confirmation
    avg_volume = mean(volumes[-20:]) if len(volumes) >= 20 else mean(volumes) if volumes else 1
    if current_volume < avg_volume * VOLUME_SPIKE_RATIO:
        return None  # Low volume — no confirmation

    # All 3 must agree
    if rsi_signal == vwap_signal:
        return rsi_signal
    return None


# ═══════════════════════════════════════════════════════════
# BACKTEST ENGINE
# ═══════════════════════════════════════════════════════════

@dataclass
class ScalpTrade:
    entry_price: float
    exit_price: float
    direction: str
    margin: float
    pnl: float
    fee: float
    tp_hits: int
    exit_reason: str
    entry_idx: int
    exit_idx: int


@dataclass
class ScalpPosition:
    direction: str
    entry_price: float
    quantity: float
    initial_quantity: float
    margin: float
    stop_loss: float
    entry_idx: int
    tp_hit: list[bool] = datafield(default_factory=lambda: [False] * 5)
    realized_pnl: float = 0.0
    tp_count: int = 0


@dataclass
class ScalpResult:
    trades: list[ScalpTrade] = datafield(default_factory=list)
    equity_curve: list[float] = datafield(default_factory=list)
    initial_equity: float = 10_000.0
    total_signals: int = 0
    filtered_signals: int = 0
    circuit_breaker_count: int = 0

    @property
    def final_equity(self) -> float:
        return self.equity_curve[-1] if self.equity_curve else self.initial_equity

    @property
    def total_return_pct(self) -> float:
        return (self.final_equity - self.initial_equity) / self.initial_equity * 100

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def winning_trades(self) -> int:
        return sum(1 for t in self.trades if t.pnl > 0)

    @property
    def win_rate(self) -> float:
        return self.winning_trades / self.total_trades if self.total_trades else 0.0

    @property
    def profit_factor(self) -> float:
        gross_profit = sum(t.pnl for t in self.trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in self.trades if t.pnl < 0))
        return gross_profit / gross_loss if gross_loss > 0 else float("inf")

    @property
    def max_drawdown_pct(self) -> float:
        if not self.equity_curve:
            return 0.0
        peak = self.equity_curve[0]
        max_dd = 0.0
        for eq in self.equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100
            if dd > max_dd:
                max_dd = dd
        return max_dd

    @property
    def sharpe_ratio(self) -> float:
        if len(self.equity_curve) < 2:
            return 0.0
        import statistics
        returns = [(self.equity_curve[i] - self.equity_curve[i-1]) / self.equity_curve[i-1]
                   for i in range(1, len(self.equity_curve))]
        if not returns:
            return 0.0
        m = statistics.mean(returns)
        s = statistics.pstdev(returns)
        if s == 0:
            return 0.0
        return (m / s) * (365 * 288) ** 0.5  # Annualize for 5min (288 candles/day)

    @property
    def avg_trade_pnl(self) -> float:
        return sum(t.pnl for t in self.trades) / self.total_trades if self.total_trades else 0.0

    def summary(self) -> str:
        tp_dist = [0] * 6  # 0=SL, 1-5=TP levels
        for t in self.trades:
            if t.tp_hits == 0:
                tp_dist[0] += 1
            else:
                tp_dist[min(t.tp_hits, 5)] += 1

        lines = [
            "═══ M5 Scalping Backtest ═══",
            f"Total signals:     {self.total_signals}",
            f"Filtered (passed): {self.filtered_signals}",
            f"Total trades:      {self.total_trades}",
            f"Win rate:          {self.win_rate:.1%}",
            f"Profit factor:     {self.profit_factor:.2f}",
            f"Total return:      {self.total_return_pct:.2f}%",
            f"Max drawdown:      {self.max_drawdown_pct:.2f}%",
            f"Sharpe ratio:      {self.sharpe_ratio:.2f}",
            f"Avg trade PnL:     ${self.avg_trade_pnl:.2f}",
            f"Final equity:      ${self.final_equity:.2f}",
            f"Circuit breakers:  {self.circuit_breaker_count}",
            f"",
            f"Exit distribution:",
            f"  SL hit:          {tp_dist[0]} ({tp_dist[0]/max(self.total_trades,1)*100:.0f}%)",
            f"  T1 (+0.03%):     {tp_dist[1]}",
            f"  T2 (+0.05%):     {tp_dist[2]}",
            f"  T3 (+0.08%):     {tp_dist[3]}",
            f"  T4 (+0.12%):     {tp_dist[4]}",
            f"  T5 (+0.18%):     {tp_dist[5]}",
        ]
        return "\n".join(lines)


def run_scalp_backtest(candles: list[list], initial_equity: float = 10_000.0) -> ScalpResult:
    """Run M5 scalping backtest on raw OHLCV candles.

    candles: [[timestamp_ms, open, high, low, close, volume], ...]
    """
    result = ScalpResult(initial_equity=initial_equity)
    equity = initial_equity
    result.equity_curve.append(equity)

    prices_buf: deque[float] = deque(maxlen=100)
    volumes_buf: deque[float] = deque(maxlen=100)

    position: Optional[ScalpPosition] = None
    consecutive_stops = 0
    pause_until_idx = 0
    daily_trades = 0
    current_day = -1

    for idx, candle in enumerate(candles):
        ts_ms, o, h, l, c, v = candle
        price = float(c)
        high = float(h)
        low = float(l)
        volume = float(v)

        prices_buf.append(price)
        volumes_buf.append(volume)

        # Reset daily counter
        day = int(ts_ms / 1000) // 86400
        if day != current_day:
            current_day = day
            daily_trades = 0

        # === CHECK EXIT FOR OPEN POSITION ===
        if position is not None:
            closed, trade = _check_scalp_exit(position, high, low, price, idx)
            if closed:
                equity += trade.pnl - trade.fee
                result.trades.append(trade)
                if trade.pnl <= 0:
                    consecutive_stops += 1
                else:
                    consecutive_stops = 0
                # Circuit breaker
                if consecutive_stops >= CONSECUTIVE_STOPS_PAUSE:
                    pause_until_idx = idx + PAUSE_CANDLES
                    result.circuit_breaker_count += 1
                    consecutive_stops = 0
                position = None
                result.equity_curve.append(equity)
                continue

        # === CHECK ENTRY ===
        if position is None and idx > pause_until_idx and daily_trades < MAX_TRADES_PER_DAY:
            if len(prices_buf) >= RSI_PERIOD + 1:
                result.total_signals += 1
                signal = bayesian_filter(price, list(prices_buf), list(volumes_buf), volume)

                if signal is not None:
                    result.filtered_signals += 1
                    margin = equity * MARGIN_PCT
                    notional = margin * LEVERAGE
                    qty = notional / price if price > 0 else 0

                    if signal == "LONG":
                        sl = price * (1 - SL_PRICE_PCT)
                    else:
                        sl = price * (1 + SL_PRICE_PCT)

                    entry_fee = notional * FEE_RATE
                    equity -= entry_fee

                    position = ScalpPosition(
                        direction=signal,
                        entry_price=price,
                        quantity=qty,
                        initial_quantity=qty,
                        margin=margin,
                        stop_loss=sl,
                        entry_idx=idx,
                    )
                    daily_trades += 1

        result.equity_curve.append(equity)

    # Force close at end
    if position is not None:
        _, trade = _check_scalp_exit(position, price, price, price, len(candles) - 1, force=True)
        equity += trade.pnl - trade.fee
        result.trades.append(trade)
        result.equity_curve[-1] = equity

    return result


def _check_scalp_exit(
    pos: ScalpPosition, high: float, low: float, close: float, idx: int, force: bool = False
) -> tuple[bool, Optional[ScalpTrade]]:
    """Check all TP levels and SL using high/low for intra-candle accuracy."""

    # Check each TP level against high (LONG) or low (SHORT)
    for i, (tp_pct, close_pct) in enumerate(TP_LEVELS):
        if pos.tp_hit[i]:
            continue

        if pos.direction == "LONG":
            tp_price = pos.entry_price * (1 + tp_pct)
            hit = high >= tp_price
        else:
            tp_price = pos.entry_price * (1 - tp_pct)
            hit = low <= tp_price

        if hit:
            pos.tp_hit[i] = True
            pos.tp_count += 1

            # Partial close
            close_qty = pos.initial_quantity * close_pct
            close_qty = min(close_qty, pos.quantity)
            if pos.direction == "LONG":
                partial_pnl = (tp_price - pos.entry_price) * close_qty
            else:
                partial_pnl = (pos.entry_price - tp_price) * close_qty
            fee = tp_price * close_qty * FEE_RATE
            pos.quantity -= close_qty
            pos.realized_pnl += partial_pnl - fee

            # Move SL to breakeven after T3
            if i >= BE_AFTER_TP:
                pos.stop_loss = pos.entry_price

            # If position fully closed
            if pos.quantity <= 0.0001:
                trade = ScalpTrade(
                    entry_price=pos.entry_price, exit_price=tp_price,
                    direction=pos.direction, margin=pos.margin,
                    pnl=pos.realized_pnl, fee=0, tp_hits=pos.tp_count,
                    exit_reason=f"T{i+1}", entry_idx=pos.entry_idx, exit_idx=idx,
                )
                return True, trade

    # Check stop loss
    if pos.direction == "LONG":
        hit_sl = low <= pos.stop_loss
        sl_price = pos.stop_loss
    else:
        hit_sl = high >= pos.stop_loss
        sl_price = pos.stop_loss

    if hit_sl or force:
        exit_price = sl_price if not force else close
        if pos.direction == "LONG":
            remaining_pnl = (exit_price - pos.entry_price) * pos.quantity
        else:
            remaining_pnl = (pos.entry_price - exit_price) * pos.quantity
        fee = exit_price * pos.quantity * FEE_RATE
        total_pnl = pos.realized_pnl + remaining_pnl - fee
        reason = "force_close" if force else ("breakeven" if pos.tp_count > 0 else "SL")
        trade = ScalpTrade(
            entry_price=pos.entry_price, exit_price=exit_price,
            direction=pos.direction, margin=pos.margin,
            pnl=total_pnl, fee=0, tp_hits=pos.tp_count,
            exit_reason=reason, entry_idx=pos.entry_idx, exit_idx=idx,
        )
        return True, trade

    return False, None


# ═══════════════════════════════════════════════════════════
# DATA DOWNLOAD + MAIN
# ═══════════════════════════════════════════════════════════

def download_m5_candles(limit: int = 1000) -> list[list]:
    """Download M5 candles from OKX."""
    import ccxt

    exchange = ccxt.okx({"enableRateLimit": True})
    symbol = "BTC/USDT:USDT"
    print(f"Downloading {limit} M5 candles for {symbol}...")

    all_candles = []
    end_ts = int(time.time() * 1000)

    while len(all_candles) < limit:
        batch = min(300, limit - len(all_candles))
        try:
            candles = exchange.fetch_ohlcv(
                symbol, "5m", limit=batch,
                params={"before": str(end_ts)} if all_candles else {},
            )
        except Exception as e:
            print(f"  error: {e}")
            break

        if not candles:
            break

        existing = {c[0] for c in all_candles}
        new = [c for c in candles if c[0] not in existing]
        if not new:
            break

        all_candles.extend(new)
        end_ts = min(c[0] for c in new)
        print(f"  fetched {len(all_candles)}/{limit}")
        time.sleep(0.3)

    all_candles.sort(key=lambda c: c[0])
    print(f"Total M5 candles: {len(all_candles)}")
    return all_candles


def main():
    csv_path = "data/okx_btc_5m.csv"

    # Try cached data first
    if os.path.exists(csv_path):
        print(f"Loading cached M5 data from {csv_path}...")
        candles = []
        with open(csv_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                candles.append([
                    int(row["timestamp"]) * 1000,
                    float(row["open"]), float(row["high"]),
                    float(row["low"]), float(row["close"]),
                    float(row["volume"]),
                ])
        print(f"Loaded {len(candles)} candles")
    else:
        candles = download_m5_candles(limit=1000)
        # Save
        os.makedirs("data", exist_ok=True)
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
            for c in candles:
                writer.writerow([int(c[0] / 1000), c[1], c[2], c[3], c[4], c[5]])
        print(f"Saved to {csv_path}")

    if len(candles) < 50:
        print("ERROR: Not enough data")
        return

    hours = len(candles) * 5 / 60
    days = hours / 24
    print(f"Data span: {hours:.0f} hours ({days:.1f} days)")
    print(f"Leverage: {LEVERAGE}x | Margin: {MARGIN_PCT*100:.0f}% | SL: {SL_PRICE_PCT*100:.1f}%")
    print(f"Filters: RSI({RSI_PERIOD}) + VWAP + Volume({VOLUME_SPIKE_RATIO}x)")
    print()

    result = run_scalp_backtest(candles)
    print(result.summary())

    # Bonus: per-day breakdown
    if result.trades:
        print(f"\n--- Per-day breakdown ---")
        from collections import defaultdict
        daily = defaultdict(lambda: {"trades": 0, "pnl": 0.0})
        for t in result.trades:
            day_ts = candles[t.entry_idx][0] // 1000 // 86400
            daily[day_ts]["trades"] += 1
            daily[day_ts]["pnl"] += t.pnl
        for day_ts in sorted(daily):
            d = daily[day_ts]
            from datetime import datetime, timezone
            dt = datetime.fromtimestamp(day_ts * 86400, tz=timezone.utc).strftime("%Y-%m-%d")
            print(f"  {dt}: {d['trades']:3d} trades, PnL: ${d['pnl']:+.2f}")


if __name__ == "__main__":
    main()
