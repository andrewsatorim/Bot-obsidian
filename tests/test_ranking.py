"""Tests for the risk-adjusted ranking in scripts/run_all_backtests.py.

Core requirement: ranking is risk-adjusted, NOT by raw return. A high-return /
high-drawdown config must lose to a moderate one with a stable equity curve.
"""
from __future__ import annotations

from scripts.run_all_backtests import rank_results


def _res(name, *, total_return_pct, max_drawdown_pct, sharpe_ratio,
         profit_factor=1.5, win_rate=0.5, expectancy=1.0, total_trades=20):
    """Build a synthetic flat metrics dict tagged with a name."""
    return {
        "name": name,
        "total_return_pct": total_return_pct,
        "max_drawdown_pct": max_drawdown_pct,
        "sharpe_ratio": sharpe_ratio,
        "profit_factor": profit_factor,
        "win_rate": win_rate,
        "expectancy": expectancy,
        "total_trades": total_trades,
    }


def test_moderate_stable_beats_high_return_high_drawdown():
    # High return but ugly Sharpe and big drawdown vs. moderate return, stable Sharpe.
    risky = _res("risky", total_return_pct=180.0, max_drawdown_pct=30.0,
                 sharpe_ratio=0.6, profit_factor=1.2)
    steady = _res("steady", total_return_pct=45.0, max_drawdown_pct=8.0,
                  sharpe_ratio=2.4, profit_factor=2.1)

    ranked = rank_results([risky, steady], max_dd_threshold=-35.0)

    winner = next(x for x in ranked if x.is_winner)
    assert winner.result["name"] == "steady"
    assert ranked[0].result["name"] == "steady"
    assert ranked[0].rank == 1
    # The high-return config is ranked strictly below the steady one.
    assert ranked[1].result["name"] == "risky"
    assert ranked[1].rank == 2


def test_drawdown_filter_excludes_blown_up_config():
    blown = _res("blown", total_return_pct=500.0, max_drawdown_pct=42.0,
                 sharpe_ratio=3.0, profit_factor=5.0)  # best metrics, but DD > 35%
    safe = _res("safe", total_return_pct=20.0, max_drawdown_pct=10.0,
                sharpe_ratio=1.1, profit_factor=1.4)

    ranked = rank_results([blown, safe], max_dd_threshold=-35.0)

    by_name = {x.result["name"]: x for x in ranked}
    # The high-DD config is filtered out despite the best Sharpe/return/PF.
    assert by_name["blown"].passed_dd_filter is False
    assert by_name["blown"].rank is None
    assert by_name["blown"].is_winner is False
    # The safe config wins by default.
    assert by_name["safe"].is_winner is True
    assert by_name["safe"].rank == 1
    # Survivors come before rejected in the returned ordering.
    assert ranked[0].result["name"] == "safe"
    assert ranked[-1].result["name"] == "blown"


def test_sharpe_primary_then_profit_factor_tiebreak():
    # Equal Sharpe -> profit_factor breaks the tie (return must NOT decide it).
    a = _res("a", total_return_pct=200.0, max_drawdown_pct=20.0,
             sharpe_ratio=1.5, profit_factor=1.3)   # huge return, lower PF
    b = _res("b", total_return_pct=30.0, max_drawdown_pct=20.0,
             sharpe_ratio=1.5, profit_factor=2.5)   # modest return, higher PF

    ranked = rank_results([a, b], max_dd_threshold=-35.0)

    assert ranked[0].result["name"] == "b"   # higher PF wins the Sharpe tie
    assert ranked[1].result["name"] == "a"


def test_threshold_sign_is_magnitude_only():
    # Passing the threshold as +35 must behave identically to -35.
    r = _res("x", total_return_pct=10.0, max_drawdown_pct=36.0,
             sharpe_ratio=1.0)
    assert rank_results([r], max_dd_threshold=-35.0)[0].passed_dd_filter is False
    assert rank_results([r], max_dd_threshold=35.0)[0].passed_dd_filter is False


def test_undefined_profit_factor_ranks_as_infinite():
    # profit_factor=None (no losing trades) should sort high on a Sharpe tie.
    flawless = _res("flawless", total_return_pct=15.0, max_drawdown_pct=5.0,
                    sharpe_ratio=1.2, profit_factor=None)
    normal = _res("normal", total_return_pct=15.0, max_drawdown_pct=5.0,
                  sharpe_ratio=1.2, profit_factor=3.0)

    ranked = rank_results([normal, flawless], max_dd_threshold=-35.0)
    assert ranked[0].result["name"] == "flawless"
