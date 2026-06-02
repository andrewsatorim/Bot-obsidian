"""Risk / sizing math for signal messages (informational only).

Given a :class:`SignalSetup` this computes entry, ATR-based stop, take-profit and
reward:risk, then — for each configured leverage — the honest profit % of deposit
at target and loss % of deposit at stop. It also answers the question the channel
actually cares about: *what leverage doubles the deposit on this trade (x2), and
what does the stop cost at that leverage?*

All numbers are net of round-trip taker fees (``fee_pct`` per side). Nothing here
touches an exchange; the reader decides whether and how big to trade.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.signal_engine.config import SignalSettings
from app.signal_engine.setups import SignalSetup


@dataclass(frozen=True)
class LeverageScenario:
    """Outcome of one leverage choice, as a percentage of deposit (net of fees)."""

    leverage: float
    profit_pct: float  # deposit % gained if take-profit is hit
    loss_pct: float    # deposit % lost if stop is hit  ("риск на стоп")


@dataclass(frozen=True)
class SignalRisk:
    """Suggested levels + leverage outcomes for a setup (purely informational)."""

    symbol: str
    direction: str
    entry: float
    stop: float
    take_profit: float
    stop_distance_pct: float    # price move from entry to stop, %
    target_distance_pct: float  # price move from entry to target, %
    risk_reward: float
    fee_round_trip_pct: float   # total fee as % of notional (both sides)
    scenarios: list[LeverageScenario]
    leverage_for_2x: float      # leverage needed to net +100% of deposit at target
    loss_pct_at_2x: float       # deposit % lost at stop when sized for x2


def compute_risk(setup: SignalSetup, settings: SignalSettings) -> SignalRisk:
    """Compute informational entry/stop/target and per-leverage outcomes."""
    entry = setup.price
    atr = setup.atr
    is_long = setup.direction == "LONG"

    stop_distance = atr * settings.atr_mult
    target_distance = stop_distance * settings.rr_target

    if is_long:
        stop = entry - stop_distance
        take_profit = entry + target_distance
    else:
        stop = entry + stop_distance
        take_profit = entry - target_distance

    # Price moves as fractions of entry (guard against a zero/degenerate price).
    stop_move = stop_distance / entry if entry > 0 else 0.0
    target_move = target_distance / entry if entry > 0 else 0.0

    # Round-trip fee as a fraction of notional (entry fill + exit fill).
    fee_rt = 2.0 * settings.fee_pct

    # PnL on a leveraged position: a price move of m (fraction) on notional = m * L
    # of the deposit/margin. Fees scale with notional too, so they also cost m_fee*L.
    def scenario(lev: float) -> LeverageScenario:
        profit = (target_move - fee_rt) * lev
        loss = (stop_move + fee_rt) * lev
        return LeverageScenario(
            leverage=lev,
            profit_pct=profit * 100.0,
            loss_pct=loss * 100.0,
        )

    # Only report leverage scenarios at or below the cap — the risk block never
    # advertises leverage the engine itself would reject (see max_leverage).
    scenarios = [scenario(lev) for lev in settings.leverages if lev <= settings.max_leverage]

    # Leverage that nets +100% of deposit at target (x2). Net move per 1x is
    # (target_move - fee_rt); if that is non-positive, x2 is unreachable.
    net_target_move = target_move - fee_rt
    if net_target_move > 0:
        leverage_for_2x = 1.0 / net_target_move
        loss_pct_at_2x = (stop_move + fee_rt) * leverage_for_2x * 100.0
    else:
        leverage_for_2x = float("inf")
        loss_pct_at_2x = float("inf")

    return SignalRisk(
        symbol=setup.symbol,
        direction=setup.direction,
        entry=entry,
        stop=stop,
        take_profit=take_profit,
        stop_distance_pct=stop_move * 100.0,
        target_distance_pct=target_move * 100.0,
        risk_reward=settings.rr_target,
        fee_round_trip_pct=fee_rt * 100.0,
        scenarios=scenarios,
        leverage_for_2x=leverage_for_2x,
        loss_pct_at_2x=loss_pct_at_2x,
    )
