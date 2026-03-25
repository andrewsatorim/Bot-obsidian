from __future__ import annotations

from app.monitoring.metrics import MetricsCollector


class TestMetricsCollector:
    def test_counter_increments(self):
        m = MetricsCollector()
        m.inc_signals("BTC", "LONG")
        m.inc_signals("BTC", "LONG")
        snapshot = m.snapshot()
        assert any(v == 2.0 for v in snapshot["counters"].values())

    def test_gauge_set(self):
        m = MetricsCollector()
        m.set_equity(15000.0)
        snapshot = m.snapshot()
        assert snapshot["gauges"]["equity"] == 15000.0

    def test_prometheus_format(self):
        m = MetricsCollector()
        m.inc_trades("BTC", "BUY")
        m.set_equity(10000.0)
        text = m.to_prometheus()
        assert "bot_obsidian_" in text
        assert "10000" in text

    def test_histogram_observe(self):
        m = MetricsCollector()
        m.observe_latency("data_feed", 0.05)
        m.observe_latency("data_feed", 0.08)
        snapshot = m.snapshot()
        assert any(v == 2 for v in snapshot["histograms"].values())
