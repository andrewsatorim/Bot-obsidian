"""Aura V14 Strategy — ported from Pine Script.

Components:
  1. Alpha Trend (MFI + ATR)
  2. Magic Trend (CCI)
  3. Consensus Engine (RSI + MFI + ADX + EMA50)
  4. UT Bot (trailing stop)
  5. Volume filter

Signal:
  BUY:  bull_sc >= 3 AND at_bull AND magic_bull AND close > n_loss AND vol_ok
  SELL: bull_sc <= 1 AND NOT at_bull AND NOT magic_bull AND close < n_loss AND vol_ok
"""
from __future__ import annotations

import logging
import math
from collections import deque
from typing import Optional

logger = logging.getLogger(__name__)


class AuraV14:
    """Aura V14 signal generator. Works on raw OHLCV candles."""

    def __init__(
        self,
        atr_period: int = 1,
        atr_multiplier: float = 5.0,
        alpha_period: int = 14,
        alpha_multiplier: float = 1.0,
        magic_period: int = 20,
        ema_period: int = 50,
        rsi_period: int = 14,
        adx_period: int = 14,
        vol_sma_period: int = 20,
    ) -> None:
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.alpha_period = alpha_period
        self.alpha_multiplier = alpha_multiplier
        self.magic_period = magic_period
        self.ema_period = ema_period
        self.rsi_period = rsi_period
        self.adx_period = adx_period
        self.vol_sma_period = vol_sma_period

        # State
        self._candles: list[list[float]] = []  # [open, high, low, close, volume]
        self._alpha_line: float = 0.0
        self._n_loss: float = 0.0
        self._trend: int = 0  # 1=bull, -1=bear, 0=neutral
        self._prev_trend: int = 0

    def update(self, o: float, h: float, l: float, c: float, v: float) -> Optional[str]:
        """Feed one candle. Returns 'BUY', 'SELL', or None."""
        self._candles.append([o, h, l, c, v])

        n = len(self._candles)
        if n < max(self.ema_period, self.alpha_period, self.magic_period, self.adx_period) + 5:
            return None

        closes = [x[3] for x in self._candles]
        highs = [x[1] for x in self._candles]
        lows = [x[2] for x in self._candles]
        volumes = [x[4] for x in self._candles]

        # --- 1. ALPHA TREND ---
        at_atr = self._sma_tr(self._candles, self.alpha_period)
        mfi = self._compute_mfi(highs, lows, closes, volumes, self.alpha_period)

        alpha_up = l - (at_atr * self.alpha_multiplier)
        alpha_dn = h + (at_atr * self.alpha_multiplier)

        if mfi >= 50:
            self._alpha_line = alpha_up if alpha_up > self._alpha_line else self._alpha_line
        else:
            self._alpha_line = alpha_dn if alpha_dn < self._alpha_line else self._alpha_line

        at_bull = c > self._alpha_line

        # --- 2. MAGIC TREND (CCI) ---
        cci = self._compute_cci(highs, lows, closes, self.magic_period)
        magic_bull = cci > 0

        # --- 3. CONSENSUS ENGINE ---
        rsi = self._compute_rsi(closes, self.rsi_period)
        adx = self._compute_adx(highs, lows, closes, self.adx_period)
        ema50 = self._ema(closes, self.ema_period)

        bull_sc = 0
        if rsi > 50: bull_sc += 1
        if mfi > 50: bull_sc += 1
        if adx > 30: bull_sc += 1
        if c > ema50: bull_sc += 1

        # --- 4. UT BOT ---
        atr = self._compute_atr(highs, lows, closes, self.atr_period)
        x_atr = atr * self.atr_multiplier

        prev_l = self._n_loss if self._n_loss != 0 else c
        prev_c = closes[-2] if n >= 2 else c

        if c > prev_l and prev_c > prev_l:
            self._n_loss = max(prev_l, c - x_atr)
        elif c < prev_l and prev_c < prev_l:
            self._n_loss = min(prev_l, c + x_atr)
        elif c > prev_l:
            self._n_loss = c - x_atr
        else:
            self._n_loss = c + x_atr

        # --- 5. VOLUME ---
        vol_sma = sum(volumes[-self.vol_sma_period:]) / self.vol_sma_period if n >= self.vol_sma_period else sum(volumes) / n
        vol_ok = v > vol_sma

        # --- SIGNAL ---
        is_bull = bull_sc >= 3 and at_bull and magic_bull and c > self._n_loss and vol_ok
        is_bear = bull_sc <= 1 and (not at_bull) and (not magic_bull) and c < self._n_loss and vol_ok

        self._prev_trend = self._trend
        if is_bull:
            self._trend = 1
        elif is_bear:
            self._trend = -1

        buy_sig = self._trend == 1 and self._prev_trend != 1
        sell_sig = self._trend == -1 and self._prev_trend != -1

        if buy_sig:
            return "BUY"
        elif sell_sig:
            return "SELL"
        return None

    @property
    def trend(self) -> int:
        return self._trend

    @property
    def n_loss(self) -> float:
        return self._n_loss

    # --- INDICATOR CALCULATIONS ---

    def _sma_tr(self, candles: list, period: int) -> float:
        if len(candles) < period + 1:
            return 0.0
        trs = []
        for i in range(-period, 0):
            h, l, c_prev = candles[i][1], candles[i][2], candles[i-1][3]
            tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
            trs.append(tr)
        return sum(trs) / len(trs) if trs else 0.0

    def _compute_atr(self, highs, lows, closes, period):
        if len(closes) < period + 1:
            return 0.0
        trs = []
        for i in range(-period, 0):
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
            trs.append(tr)
        return sum(trs) / len(trs) if trs else 0.0

    def _compute_rsi(self, closes, period):
        if len(closes) < period + 1:
            return 50.0
        changes = [closes[i] - closes[i-1] for i in range(-period, 0)]
        gains = [c for c in changes if c > 0]
        losses = [-c for c in changes if c < 0]
        avg_gain = sum(gains) / period if gains else 0.0
        avg_loss = sum(losses) / period if losses else 0.0001
        rs = avg_gain / avg_loss if avg_loss > 0 else 100
        return 100 - (100 / (1 + rs))

    def _compute_mfi(self, highs, lows, closes, volumes, period):
        if len(closes) < period + 1:
            return 50.0
        pos_flow = 0.0
        neg_flow = 0.0
        for i in range(-period, 0):
            tp = (highs[i] + lows[i] + closes[i]) / 3
            tp_prev = (highs[i-1] + lows[i-1] + closes[i-1]) / 3
            mf = tp * volumes[i]
            if tp > tp_prev:
                pos_flow += mf
            else:
                neg_flow += mf
        if neg_flow == 0:
            return 100.0
        ratio = pos_flow / neg_flow
        return 100 - (100 / (1 + ratio))

    def _compute_cci(self, highs, lows, closes, period):
        if len(closes) < period:
            return 0.0
        tps = [(highs[i] + lows[i] + closes[i]) / 3 for i in range(-period, 0)]
        tp_mean = sum(tps) / period
        mean_dev = sum(abs(tp - tp_mean) for tp in tps) / period
        if mean_dev == 0:
            return 0.0
        return (tps[-1] - tp_mean) / (0.015 * mean_dev)

    def _compute_adx(self, highs, lows, closes, period):
        if len(closes) < period + 2:
            return 0.0
        plus_dm_sum = 0.0
        minus_dm_sum = 0.0
        tr_sum = 0.0
        for i in range(-period, 0):
            up = highs[i] - highs[i-1]
            down = lows[i-1] - lows[i]
            plus_dm = up if up > down and up > 0 else 0
            minus_dm = down if down > up and down > 0 else 0
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
            plus_dm_sum += plus_dm
            minus_dm_sum += minus_dm
            tr_sum += tr
        if tr_sum == 0:
            return 0.0
        plus_di = (plus_dm_sum / tr_sum) * 100
        minus_di = (minus_dm_sum / tr_sum) * 100
        dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) > 0 else 0
        return dx

    def _ema(self, data, period):
        if len(data) < period:
            return data[-1] if data else 0.0
        k = 2.0 / (period + 1)
        ema = sum(data[-period:]) / period  # SMA seed
        # Apply EMA on last 'period' values
        for i in range(-period + 1, 0):
            ema = data[i] * k + ema * (1 - k)
        return ema
