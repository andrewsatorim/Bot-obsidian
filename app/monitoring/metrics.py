from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class MetricPoint:
    name: str
    value: float
    timestamp: float
    labels: dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """In-process metrics collector. Exposes Prometheus-compatible text format.

    Tracks counters, gauges, and histograms for trading operations.
    """

    def __init__(self) -> None:
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._start_time = time.time()

    # -- Counters --

    def inc_signals(self, symbol: str, direction: str) -> None:
        self._counters[f"signals_total{{symbol=\"{symbol}\",direction=\"{direction}\"}}"] += 1

    def inc_trades(self, symbol: str, side: str) -> None:
        self._counters[f"trades_total{{symbol=\"{symbol}\",side=\"{side}\"}}"] += 1

    def inc_rejections(self, reason: str) -> None:
        self._counters[f"risk_rejections_total{{reason=\"{reason}\"}}"] += 1

    def inc_errors(self, component: str) -> None:
        self._counters[f"errors_total{{component=\"{component}\"}}"] += 1

    def inc_state_transitions(self, from_state: str, to_state: str) -> None:
        self._counters[f"state_transitions_total{{from=\"{from_state}\",to=\"{to_state}\"}}"] += 1

    # -- Gauges --

    def set_equity(self, value: float) -> None:
        self._gauges["equity"] = value

    def set_daily_pnl(self, value: float) -> None:
        self._gauges["daily_pnl"] = value

    def set_open_positions(self, count: int) -> None:
        self._gauges["open_positions"] = float(count)

    def set_unrealized_pnl(self, symbol: str, value: float) -> None:
        self._gauges[f"unrealized_pnl{{symbol=\"{symbol}\"}}"] = value

    def set_engine_state(self, symbol: str, state: str) -> None:
        self._gauges[f"engine_state{{symbol=\"{symbol}\",state=\"{state}\"}}"] = 1.0

    # -- Histograms --

    def observe_latency(self, component: str, seconds: float) -> None:
        self._histograms[f"latency_seconds{{component=\"{component}\"}}"].append(seconds)

    def observe_slippage(self, symbol: str, slippage_pct: float) -> None:
        self._histograms[f"slippage_pct{{symbol=\"{symbol}\"}}"].append(slippage_pct)

    # -- Export --

    def to_prometheus(self) -> str:
        """Export all metrics in Prometheus text exposition format."""
        lines: list[str] = []
        lines.append(f"# Bot-Obsidian metrics (uptime={time.time() - self._start_time:.0f}s)")

        for key, val in sorted(self._counters.items()):
            lines.append(f"bot_obsidian_{key} {val}")

        for key, val in sorted(self._gauges.items()):
            lines.append(f"bot_obsidian_{key} {val}")

        for key, values in sorted(self._histograms.items()):
            if values:
                import statistics
                lines.append(f"bot_obsidian_{key}_count {len(values)}")
                lines.append(f"bot_obsidian_{key}_sum {sum(values):.6f}")
                lines.append(f"bot_obsidian_{key}_avg {statistics.mean(values):.6f}")

        return "\n".join(lines)

    def snapshot(self) -> dict:
        """Return a dict snapshot of all metrics for JSON export."""
        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {k: len(v) for k, v in self._histograms.items()},
            "uptime_seconds": time.time() - self._start_time,
        }
