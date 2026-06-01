"""Signal engine orchestration: scan -> select setups -> risk -> Telegram text.

The ONLY side effect is ``notifier.send(text)``. There is deliberately no
executor, orchestrator, order or position anywhere in the flow. Market data
comes from an injected read-only source (a small Protocol), so the package never
has to import a concrete feed and tests can run without the network.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from app.analytics.feature_engine import FeatureEngine
from app.models.market_data_bundle import MarketDataBundle
from app.signal_engine.config import SignalSettings
from app.signal_engine.notifier import TelegramSignalNotifier
from app.signal_engine.risk import SignalRisk, compute_risk
from app.signal_engine.setups import SignalSetup, select_setups

logger = logging.getLogger(__name__)

_FACTOR_LABELS = {
    "signal": "сигнал стратегии",
    "regime": "тренд (не флэт)",
    "liquidity": "зона ликвидности",
    "oi": "дисбаланс OI",
}


class MarketDataSource(Protocol):
    """Read-only market data provider (e.g. CcxtDataFeed). No execution surface."""

    async def get_market_data(self, symbol: str) -> MarketDataBundle: ...


def _fmt_price(value: float) -> str:
    """Compact price formatting that stays readable across BTC and alt prices."""
    if value >= 100:
        return f"{value:,.2f}"
    if value >= 1:
        return f"{value:.4f}"
    return f"{value:.6f}"


def format_signal_message(setup: SignalSetup, risk: SignalRisk) -> str:
    """Render a setup + risk into a concise Russian Telegram message."""
    arrow = "🟢 LONG" if setup.direction == "LONG" else "🔴 SHORT"
    matched = [_FACTOR_LABELS[k] for k in setup.factors if setup.factors[k]]

    lines = [
        f"{arrow}  {setup.symbol}",
        f"Качество сетапа: {setup.quality * 100:.0f}%  ({', '.join(matched)})",
        f"Стратегия даёт силу: {setup.strength:.2f} | режим: {setup.regime}",
        "",
        f"Вход:  {_fmt_price(risk.entry)}",
        f"Стоп:  {_fmt_price(risk.stop)}  (−{risk.stop_distance_pct:.2f}% хода)",
        f"Цель:  {_fmt_price(risk.take_profit)}  (+{risk.target_distance_pct:.2f}% хода)",
        f"R:R = 1:{risk.risk_reward:.1f}  | комиссия туда-обратно {risk.fee_round_trip_pct:.2f}%",
        "",
        "Риск на стоп (от депозита, с учётом комиссии):",
    ]
    for sc in risk.scenarios:
        lines.append(
            f"  x{sc.leverage:.0f}: прибыль по цели +{sc.profit_pct:.0f}% / "
            f"убыток по стопу −{sc.loss_pct:.0f}%"
        )

    if risk.leverage_for_2x == float("inf"):
        lines.append("")
        lines.append("Для x2 за сделку: недостижимо при таком ходе цены.")
    else:
        lines.append("")
        lines.append(
            f"Для x2 за сделку нужно плечо ≈ x{risk.leverage_for_2x:.0f}, "
            f"и тогда стоп стоит −{risk.loss_pct_at_2x:.0f}% депозита."
        )

    lines.append("")
    lines.append("⚠️ Решение о размере — за тобой.")
    return "\n".join(lines)


class SignalEngine:
    """Scans the configured universe and emits text-only Telegram alerts."""

    def __init__(
        self,
        settings: SignalSettings,
        notifier: TelegramSignalNotifier,
        data_source: MarketDataSource,
        feature_engine: FeatureEngine | None = None,
    ) -> None:
        self._settings = settings
        self._notifier = notifier
        self._data_source = data_source
        self._feature_engine = feature_engine or FeatureEngine()

    async def _collect_bundles(self) -> dict[str, MarketDataBundle]:
        bundles: dict[str, MarketDataBundle] = {}
        for symbol in self._settings.symbols:
            try:
                bundles[symbol] = await self._data_source.get_market_data(symbol)
            except Exception:
                logger.exception("failed to fetch market data for %s", symbol)
        return bundles

    async def run_once(self) -> list[SignalSetup]:
        """One scan pass: collect data, select setups, notify on each passing one."""
        bundles = await self._collect_bundles()
        setups = select_setups(bundles, self._settings, self._feature_engine)
        for setup in setups:
            risk = compute_risk(setup, self._settings)
            await self._notifier.send(format_signal_message(setup, risk))
        logger.info("scan complete: %d setup(s) notified", len(setups))
        return setups

    async def run_forever(self) -> None:
        """Scan loop — one pass every ``scan_interval_sec`` from the config."""
        logger.info(
            "signal engine started: %d symbol(s), strategy=%s, interval=%.0fs",
            len(self._settings.symbols),
            self._settings.strategy_name,
            self._settings.scan_interval_sec,
        )
        while True:
            try:
                await self.run_once()
            except Exception:
                logger.exception("scan pass failed")
            await asyncio.sleep(self._settings.scan_interval_sec)
