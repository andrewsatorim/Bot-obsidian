"""Setup selection for the signal engine (read-only, never executes).

A setup is a symbol worth a Telegram alert. We build a :class:`FeatureVector`
with the existing :class:`FeatureEngine`, run a configurable strategy over it,
then score the setup 0..1 as the fraction of four independent factors that line
up in the signal's direction:

    (a) the strategy produced a signal of sufficient strength,
    (b) the regime is a real trend (TREND_UP/TREND_DOWN), not RANGE,
    (c) there is a liquidity cluster from the coinglass heatmap in the signal's
        direction (price tends to get pulled toward resting liquidations),
    (d) open interest is building (fresh positions backing the move).

Only setups with ``quality >= settings.min_quality`` are returned. This module
imports only read-only analytics/strategy code — no executor, order or port.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from app.analytics.feature_engine import FeatureEngine
from app.models.enums import Direction, RegimeLabel
from app.models.feature_vector import FeatureVector
from app.models.signal import Signal
from app.ports.strategy_port import StrategyPort
from app.signal_engine.config import SignalSettings
from app.signal_engine.market_data import FactorAvailability, SymbolFeed
from app.strategy.breakout import BreakoutStrategy
from app.strategy.donchian import DonchianStrategy
from app.strategy.oi_divergence import OIDivergenceStrategy
from app.strategy.swing import SwingStrategy
from app.strategy.trend_following import TrendFollowingStrategy

logger = logging.getLogger(__name__)

# Configurable strategy surface for the signal engine. Trend following is the
# default because it is the most walk-forward-robust of the set. These are the
# SAME strategy classes the main bot uses — we only READ their signals here.
STRATEGY_FACTORIES: dict[str, Callable[[str], StrategyPort]] = {
    "TrendFollowing": lambda s: TrendFollowingStrategy(symbol=s),
    "Breakout": lambda s: BreakoutStrategy(symbol=s),
    "Donchian": lambda s: DonchianStrategy(symbol=s),
    "Swing": lambda s: SwingStrategy(symbol=s),
    "OIDivergence": lambda s: OIDivergenceStrategy(symbol=s),
}

FACTOR_KEYS = ("signal", "regime", "liquidity", "oi")


@dataclass(frozen=True)
class SignalSetup:
    """A detected setup worth notifying about (no execution semantics).

    ``factors`` is tri-state: ``True`` matched, ``False`` evaluated-but-not-matched,
    ``None`` data unavailable (e.g. Coinglass not configured).
    """

    symbol: str
    direction: str  # "LONG" | "SHORT"
    strength: float
    quality: float
    factors: dict[str, bool | None]
    price: float
    atr: float
    regime: str
    reason: str


def build_strategy(name: str, symbol: str) -> StrategyPort:
    """Instantiate the configured strategy, defaulting to trend following."""
    factory = STRATEGY_FACTORIES.get(name)
    if factory is None:
        logger.warning("unknown strategy %r, falling back to TrendFollowing", name)
        factory = STRATEGY_FACTORIES["TrendFollowing"]
    return factory(symbol)


def score_factors(
    features: FeatureVector,
    signal: Signal,
    settings: SignalSettings,
    availability: FactorAvailability | None = None,
) -> dict[str, bool | None]:
    """Evaluate the four quality factors. Data-less factors return ``None``.

    ``availability`` says whether the liquidity/OI data is actually present; when
    it isn't, those factors are ``None`` ("data unavailable") rather than ``False``,
    so a missing Coinglass feed is never mistaken for an evaluated failure or pass.
    """
    avail = availability or FactorAvailability()
    is_long = signal.direction == Direction.LONG

    # (a) strategy signal strong enough
    f_signal = signal.strength >= settings.min_confidence

    # (b) confirmed trend regime aligned with the signal direction
    if is_long:
        f_regime = features.regime_label == RegimeLabel.TREND_UP
    else:
        f_regime = features.regime_label == RegimeLabel.TREND_DOWN

    # (c) liquidity cluster (coinglass heatmap) sits in the signal's direction
    f_liquidity: bool | None
    if not avail.liquidity:
        f_liquidity = None
    elif is_long:
        f_liquidity = features.liquidation_above > features.liquidation_below and features.liquidation_above > 0
    else:
        f_liquidity = features.liquidation_below > features.liquidation_above and features.liquidation_below > 0

    # (d) open interest building (fresh positions backing the move)
    f_oi: bool | None
    if not avail.oi:
        f_oi = None
    else:
        f_oi = features.oi_delta > settings.min_oi_imbalance and features.oi_trend > 0

    return {"signal": f_signal, "regime": f_regime, "liquidity": f_liquidity, "oi": f_oi}


def quality_from_factors(factors: dict[str, bool | None]) -> float:
    """Quality 0..1 = matched factors / four. Unavailable (``None``) factors can
    never contribute, so missing data lowers the ceiling instead of inflating it."""
    return sum(1 for k in FACTOR_KEYS if factors.get(k) is True) / len(FACTOR_KEYS)


def evaluate_symbol(
    symbol: str,
    feed: SymbolFeed,
    strategy: StrategyPort,
    settings: SignalSettings,
    feature_engine: FeatureEngine | None = None,
) -> SignalSetup | None:
    """Build features, run the strategy, score it. Returns a setup or ``None``."""
    engine = feature_engine or FeatureEngine()
    features = engine.build_features(feed.bundle)
    signal = strategy.generate_signal(features)
    if signal is None:
        return None

    factors = score_factors(features, signal, settings, feed.availability)
    quality = quality_from_factors(factors)
    if quality < settings.min_quality:
        logger.debug("%s below min_quality: %.2f < %.2f", symbol, quality, settings.min_quality)
        return None

    matched = [k for k in FACTOR_KEYS if factors[k] is True]
    return SignalSetup(
        symbol=symbol,
        direction=signal.direction.value,
        strength=signal.strength,
        quality=quality,
        factors=factors,
        price=features.price,
        atr=features.atr,
        regime=features.regime_label.value,
        reason="+".join(matched),
    )


def select_setups(
    feeds: dict[str, SymbolFeed],
    settings: SignalSettings,
    feature_engine: FeatureEngine | None = None,
) -> list[SignalSetup]:
    """Score every symbol and return the passing setups, best quality first."""
    engine = feature_engine or FeatureEngine()
    setups: list[SignalSetup] = []
    for symbol, feed in feeds.items():
        strategy = build_strategy(settings.strategy_name, symbol)
        setup = evaluate_symbol(symbol, feed, strategy, settings, engine)
        if setup is not None:
            setups.append(setup)
    setups.sort(key=lambda s: s.quality, reverse=True)
    return setups
