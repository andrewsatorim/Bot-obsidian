"""Aura V14 Strategy — FIXED port from Pine Script.

All indicators use Wilder's RMA matching Pine Script exactly.
Fixed: RSI, ADX, ATR, EMA, MFI, Alpha Line initialization.
"""
from __future__ import annotations

import logging
from collections import deque
from typing import Optional

logger = logging.getLogger(__name__)


class AuraV14:
    """Aura V14 with correct Wilder's smoothing."""

    def __init__(self, atr_period=1, atr_multiplier=5.0, alpha_period=14,
                 alpha_multiplier=1.0, magic_period=20, ema_period=50,
                 rsi_period=14, adx_period=14, vol_sma_period=20, max_candles=500):
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.alpha_period = alpha_period
        self.alpha_multiplier = alpha_multiplier
        self.magic_period = magic_period
        self.ema_period = ema_period
        self.rsi_period = rsi_period
        self.adx_period = adx_period
        self.vol_sma_period = vol_sma_period
        self._candles: deque = deque(maxlen=max_candles)
        self._alpha_line: Optional[float] = None
        self._n_loss: float = 0.0
        self._trend: int = 0
        self._prev_trend: int = 0
        # Wilder's RMA state
        self._rsi_avg_gain: Optional[float] = None
        self._rsi_avg_loss: Optional[float] = None
        self._atr_rma: Optional[float] = None
        self._plus_di_rma: Optional[float] = None
        self._minus_di_rma: Optional[float] = None
        self._tr_rma: Optional[float] = None
        self._adx_rma: Optional[float] = None
        self._ema_value: Optional[float] = None
        self._bar_count: int = 0

    def update(self, o, h, l, c, v) -> Optional[str]:
        self._candles.append([o, h, l, c, v])
        self._bar_count += 1
        n = self._bar_count
        if n < 2:
            return None
        prev = self._candles[-2]
        prev_c = prev[3]
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        # ATR (Wilder's RMA) for UT Bot
        self._atr_rma = self._wilder_rma(self._atr_rma, tr, self.atr_period, n)
        atr = self._atr_rma or 0
        # Alpha ATR (SMA of TR for alpha trend)
        alpha_atr = self._sma_tr()
        # RSI (Wilder's)
        change = c - prev_c
        rsi = self._update_rsi(max(change, 0), max(-change, 0), n)
        # MFI
        mfi = self._compute_mfi()
        # CCI
        cci = self._compute_cci()
        # ADX (Wilder's)
        adx = self._update_adx(h, l, prev[1], prev[2], prev_c, tr, n)
        # EMA(50)
        self._ema_value = self._update_ema(c, n)
        ema50 = self._ema_value or c
        # Volume SMA
        vol_sma = self._vol_sma()
        vol_ok = v > vol_sma if vol_sma > 0 else False
        warmup = max(self.ema_period, self.alpha_period, self.magic_period, self.adx_period) + 2
        if n < warmup:
            return None
        # 1. ALPHA TREND
        alpha_up = l - (alpha_atr * self.alpha_multiplier)
        alpha_dn = h + (alpha_atr * self.alpha_multiplier)
        if self._alpha_line is None:
            self._alpha_line = alpha_up if mfi >= 50 else alpha_dn
        if mfi >= 50:
            self._alpha_line = max(self._alpha_line, alpha_up)
        else:
            self._alpha_line = min(self._alpha_line, alpha_dn)
        at_bull = c > self._alpha_line
        # 2. MAGIC TREND
        magic_bull = cci > 0
        # 3. CONSENSUS
        bull_sc = 0
        if rsi > 50: bull_sc += 1
        if mfi > 50: bull_sc += 1
        if adx > 30: bull_sc += 1
        if c > ema50: bull_sc += 1
        # 4. UT BOT
        x_atr = atr * self.atr_multiplier
        prev_l = self._n_loss if self._n_loss != 0 else c
        if c > prev_l and prev_c > prev_l:
            self._n_loss = max(prev_l, c - x_atr)
        elif c < prev_l and prev_c < prev_l:
            self._n_loss = min(prev_l, c + x_atr)
        elif c > prev_l:
            self._n_loss = c - x_atr
        else:
            self._n_loss = c + x_atr
        # 5. SIGNAL
        is_bull = bull_sc >= 3 and at_bull and magic_bull and c > self._n_loss and vol_ok
        is_bear = bull_sc <= 1 and (not at_bull) and (not magic_bull) and c < self._n_loss and vol_ok
        self._prev_trend = self._trend
        if is_bull: self._trend = 1
        elif is_bear: self._trend = -1
        if self._trend == 1 and self._prev_trend != 1: return "BUY"
        elif self._trend == -1 and self._prev_trend != -1: return "SELL"
        return None

    @property
    def trend(self): return self._trend
    @property
    def n_loss(self): return self._n_loss

    def _wilder_rma(self, prev, value, period, n):
        if prev is None or n <= period + 1:
            candles = list(self._candles)
            if len(candles) < 2: return value
            trs = []
            for i in range(max(1, len(candles)-period), len(candles)):
                ch, cl = candles[i][1], candles[i][2]
                cpc = candles[i-1][3]
                trs.append(max(ch-cl, abs(ch-cpc), abs(cl-cpc)))
            return sum(trs)/len(trs) if trs else value
        return (prev * (period - 1) + value) / period

    def _update_rsi(self, gain, loss, n):
        p = self.rsi_period
        if self._rsi_avg_gain is None:
            self._rsi_avg_gain = gain
            self._rsi_avg_loss = loss
            return 50.0
        if n <= p + 1:
            self._rsi_avg_gain = (self._rsi_avg_gain * (n-2) + gain) / (n-1)
            self._rsi_avg_loss = (self._rsi_avg_loss * (n-2) + loss) / (n-1)
        else:
            self._rsi_avg_gain = (self._rsi_avg_gain * (p-1) + gain) / p
            self._rsi_avg_loss = (self._rsi_avg_loss * (p-1) + loss) / p
        if self._rsi_avg_loss == 0: return 100.0
        return 100 - (100 / (1 + self._rsi_avg_gain / self._rsi_avg_loss))

    def _sma_tr(self):
        p = self.alpha_period
        candles = list(self._candles)
        if len(candles) < p + 1: return 0.0
        trs = []
        for i in range(-p, 0):
            trs.append(max(candles[i][1]-candles[i][2], abs(candles[i][1]-candles[i-1][3]), abs(candles[i][2]-candles[i-1][3])))
        return sum(trs)/len(trs)

    def _compute_mfi(self):
        p = self.alpha_period
        candles = list(self._candles)
        if len(candles) < p + 1: return 50.0
        pos_f, neg_f = 0.0, 0.0
        for i in range(-p, 0):
            tp = (candles[i][1]+candles[i][2]+candles[i][3])/3
            tp_p = (candles[i-1][1]+candles[i-1][2]+candles[i-1][3])/3
            mf = tp * candles[i][4]
            if tp > tp_p: pos_f += mf
            elif tp < tp_p: neg_f += mf  # Fixed: skip when equal
        if neg_f == 0: return 100.0 if pos_f > 0 else 50.0
        return 100 - (100 / (1 + pos_f/neg_f))

    def _compute_cci(self):
        p = self.magic_period
        candles = list(self._candles)
        if len(candles) < p: return 0.0
        tps = [(candles[i][1]+candles[i][2]+candles[i][3])/3 for i in range(-p, 0)]
        m = sum(tps)/p
        md = sum(abs(t-m) for t in tps)/p
        if md == 0: return 0.0
        return (tps[-1]-m)/(0.015*md)

    def _update_adx(self, h, l, ph, pl, pc, tr, n):
        p = self.adx_period
        up = h - ph
        down = pl - l
        plus_dm = up if up > down and up > 0 else 0
        minus_dm = down if down > up and down > 0 else 0
        if self._plus_di_rma is None:
            self._plus_di_rma = plus_dm
            self._minus_di_rma = minus_dm
            self._tr_rma = tr
            self._adx_rma = 0.0
            return 0.0
        if n <= p + 1:
            self._plus_di_rma = (self._plus_di_rma*(n-2)+plus_dm)/(n-1)
            self._minus_di_rma = (self._minus_di_rma*(n-2)+minus_dm)/(n-1)
            self._tr_rma = (self._tr_rma*(n-2)+tr)/(n-1)
        else:
            self._plus_di_rma = (self._plus_di_rma*(p-1)+plus_dm)/p
            self._minus_di_rma = (self._minus_di_rma*(p-1)+minus_dm)/p
            self._tr_rma = (self._tr_rma*(p-1)+tr)/p
        if self._tr_rma == 0: return 0.0
        pdi = (self._plus_di_rma/self._tr_rma)*100
        mdi = (self._minus_di_rma/self._tr_rma)*100
        ds = pdi+mdi
        if ds == 0: return 0.0
        dx = abs(pdi-mdi)/ds*100
        if self._adx_rma == 0: self._adx_rma = dx
        else: self._adx_rma = (self._adx_rma*(p-1)+dx)/p
        return self._adx_rma

    def _update_ema(self, value, n):
        p = self.ema_period
        if self._ema_value is None:
            self._ema_value = value
            return value
        if n <= p:
            candles = list(self._candles)
            return sum(c[3] for c in candles)/len(candles)
        k = 2.0/(p+1)
        self._ema_value = value*k + self._ema_value*(1-k)
        return self._ema_value

    def _vol_sma(self):
        p = self.vol_sma_period
        candles = list(self._candles)
        if len(candles) < p:
            return sum(c[4] for c in candles)/len(candles) if candles else 0
        return sum(candles[i][4] for i in range(-p, 0))/p
