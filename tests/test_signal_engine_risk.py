"""Unit tests for signal-engine risk math — exact numbers, no network."""

from __future__ import annotations

import math

from app.signal_engine.config import SignalSettings
from app.signal_engine.risk import compute_risk
from app.signal_engine.setups import SignalSetup


def _setup(direction: str = "LONG", price: float = 100.0, atr: float = 2.0) -> SignalSetup:
    return SignalSetup(
        symbol="BTC/USDT:USDT",
        direction=direction,
        strength=0.8,
        quality=1.0,
        factors={"signal": True, "regime": True, "liquidity": True, "oi": True},
        price=price,
        atr=atr,
        regime="TREND_UP",
        reason="signal+regime+liquidity+oi",
    )


def test_levels_and_distances_no_fees() -> None:
    """entry=100, atr=2, atr_mult=1.5 -> stop 3% away, target (R:R 2) 6% away."""
    settings = SignalSettings(atr_mult=1.5, rr_target=2.0, fee_pct=0.0, leverages=[20, 30, 40])
    risk = compute_risk(_setup(), settings)

    assert risk.entry == 100.0
    assert risk.stop == 97.0  # 100 - 2*1.5
    assert risk.take_profit == 106.0  # 100 + 3*2
    assert math.isclose(risk.stop_distance_pct, 3.0)
    assert math.isclose(risk.target_distance_pct, 6.0)
    assert math.isclose(risk.risk_reward, 2.0)


def test_short_levels_mirror() -> None:
    settings = SignalSettings(atr_mult=1.5, rr_target=2.0, fee_pct=0.0)
    risk = compute_risk(_setup(direction="SHORT"), settings)
    assert risk.stop == 103.0
    assert risk.take_profit == 94.0


def test_leverage_loss_pct_no_fees() -> None:
    """3% stop move -> loss% of deposit = 3% * leverage."""
    settings = SignalSettings(atr_mult=1.5, rr_target=2.0, fee_pct=0.0, leverages=[20, 30, 40])
    risk = compute_risk(_setup(), settings)
    by_lev = {s.leverage: s for s in risk.scenarios}

    assert math.isclose(by_lev[20].loss_pct, 60.0)  # 3% * 20
    assert math.isclose(by_lev[30].loss_pct, 90.0)  # 3% * 30
    assert math.isclose(by_lev[40].loss_pct, 120.0)  # 3% * 40 -> stop wipes >100%
    assert math.isclose(by_lev[20].profit_pct, 120.0)  # 6% * 20


def test_leverage_for_2x_no_fees() -> None:
    """Target is +6% move; doubling deposit needs L = 100% / 6% ~= 16.67x."""
    settings = SignalSettings(atr_mult=1.5, rr_target=2.0, fee_pct=0.0)
    risk = compute_risk(_setup(), settings)

    assert math.isclose(risk.leverage_for_2x, 100.0 / 6.0, rel_tol=1e-9)  # ~16.667
    # At that leverage the 3% stop costs 3% * 16.667 = 50% of deposit.
    assert math.isclose(risk.loss_pct_at_2x, 50.0, rel_tol=1e-9)


def test_fees_reduce_profit_and_raise_loss() -> None:
    """With 0.05% per side (0.1% round-trip), profit shrinks and loss grows."""
    settings = SignalSettings(atr_mult=1.5, rr_target=2.0, fee_pct=0.0005, leverages=[20])
    risk = compute_risk(_setup(), settings)
    sc = risk.scenarios[0]

    assert math.isclose(risk.fee_round_trip_pct, 0.1)
    # profit = (6% - 0.1%) * 20 = 118%; loss = (3% + 0.1%) * 20 = 62%
    assert math.isclose(sc.profit_pct, 118.0, rel_tol=1e-9)
    assert math.isclose(sc.loss_pct, 62.0, rel_tol=1e-9)
    # leverage_for_2x = 1 / (6% - 0.1%) = 1/0.059 ~= 16.95x
    assert math.isclose(risk.leverage_for_2x, 1.0 / 0.059, rel_tol=1e-9)


def test_unreachable_2x_when_target_below_fees() -> None:
    """If the target move can't cover fees, x2 is reported as unreachable."""
    settings = SignalSettings(atr_mult=0.0001, rr_target=1.0, fee_pct=0.05)
    risk = compute_risk(_setup(), settings)
    assert risk.leverage_for_2x == float("inf")
    assert risk.loss_pct_at_2x == float("inf")
