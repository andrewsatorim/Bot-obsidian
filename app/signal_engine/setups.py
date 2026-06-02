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
from dataclasses import dataclass, field

from app.analytics.feature_engine import FeatureEngine
from app.models.enums import Direction, RegimeLabel
from app.models.feature_vector import FeatureVector
from app.models.market_data_bundle import MarketDataBundle
from app.models.signal import Signal
from app.ports.strategy_port import StrategyPort
from app.signal_engine.config import SignalSettings
from app.signal_engine.context import ContextCache, ContextDirection
from app.signal_engine.market_data import FactorAvailability
from app.signal_engine.multi_tf import MultiTFData, MultiTimeframeCollector
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
    # Multi-timeframe breakdown (defaulted so single-TF construction still works).
    eval_votes: dict[str, bool] = field(default_factory=dict)  # eval TF -> aligned?
    eval_agreement: float = 0.0                                # fraction of eval TFs aligned
    context: str = "NEUTRAL"                                   # ContextDirection value
    context_score: float = 0.0                                # context contribution 0..1
    entry_aligned: bool = False                                # entry-TF momentum aligned?


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


_ENTRY_MOMENTUM_LOOKBACK = 3


def regime_aligns(regime: RegimeLabel, is_long: bool) -> bool:
    """A timeframe's regime agrees with the setup direction (TREND_UP for LONG)."""
    return regime == (RegimeLabel.TREND_UP if is_long else RegimeLabel.TREND_DOWN)


def context_alignment_score(
    context: ContextDirection, is_long: bool, neutral_score: float
) -> float:
    """Context contribution 0..1: aligned -> 1, neutral -> neutral_score, opposed -> 0."""
    if context == ContextDirection.NEUTRAL:
        return neutral_score
    aligned = (context == ContextDirection.BULLISH) == is_long
    return 1.0 if aligned else 0.0


def entry_momentum_aligned(bundle: MarketDataBundle, is_long: bool) -> bool:
    """Short-term momentum on the entry timeframe points the setup's way."""
    prices = bundle.price_history
    if len(prices) < 2:
        return False
    k = min(_ENTRY_MOMENTUM_LOOKBACK, len(prices) - 1)
    momentum = prices[-1] - prices[-1 - k]
    if momentum == 0:
        return False
    return (momentum > 0) == is_long


def compute_quality(
    factors: dict[str, bool | None],
    eval_agreement: float,
    context_score: float,
    entry_score: float,
    settings: SignalSettings,
) -> float:
    """Weighted setup quality 0..1 — a SOFT blend, not hard gates.

    quality = sum(weight_i * score_i) / sum(weight_i over AVAILABLE i). The two
    Coinglass factors are tri-state: when their data is unavailable (``None``)
    they are excluded from BOTH numerator and denominator, so missing data lowers
    the ceiling honestly instead of counting as a pass or a penalised fail.
    """
    parts: list[tuple[float, float]] = [
        (settings.weight_signal, 1.0 if factors["signal"] else 0.0),
        (settings.weight_regime, 1.0 if factors["regime"] else 0.0),
        (settings.weight_eval_tf, eval_agreement),
        (settings.weight_context, context_score),
        (settings.weight_entry, entry_score),
    ]
    if factors.get("liquidity") is not None:
        parts.append((settings.weight_liquidity, 1.0 if factors["liquidity"] else 0.0))
    if factors.get("oi") is not None:
        parts.append((settings.weight_oi, 1.0 if factors["oi"] else 0.0))

    total_weight = sum(w for w, _ in parts)
    if total_weight <= 0:
        return 0.0
    return sum(w * s for w, s in parts) / total_weight


def evaluate_symbol(
    symbol: str,
    mtf: MultiTFData,
    context: ContextDirection,
    strategy: StrategyPort,
    settings: SignalSettings,
    feature_engine: FeatureEngine | None = None,
) -> SignalSetup | None:
    """Score one symbol across timeframes. Returns a setup or ``None``.

    The strategy runs on the SETUP-timeframe features (its logic is untouched).
    The four existing factors are scored on the setup TF; the evaluation TFs each
    cast a direction vote (consensus); the cached context and entry-TF momentum
    add their soft contributions. Quality is the weighted blend (``compute_quality``).
    """
    engine = feature_engine or FeatureEngine()
    setup_features = engine.build_features(mtf.setup)
    signal = strategy.generate_signal(setup_features)
    if signal is None:
        return None
    is_long = signal.direction == Direction.LONG

    factors = score_factors(setup_features, signal, settings, mtf.availability)

    # Evaluation-TF consensus: each eval timeframe votes for/against the direction.
    eval_votes = {
        tf: regime_aligns(engine.build_features(bundle).regime_label, is_long)
        for tf, bundle in mtf.evals.items()
    }
    eval_agreement = (
        sum(1 for v in eval_votes.values() if v) / len(eval_votes) if eval_votes else 0.0
    )

    context_score = context_alignment_score(context, is_long, settings.context_neutral_score)
    entry_aligned = entry_momentum_aligned(mtf.entry, is_long)
    entry_score = 1.0 if entry_aligned else 0.0

    quality = compute_quality(factors, eval_agreement, context_score, entry_score, settings)
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
        price=setup_features.price,
        atr=setup_features.atr,
        regime=setup_features.regime_label.value,
        reason="+".join(matched),
        eval_votes=eval_votes,
        eval_agreement=eval_agreement,
        context=context.value,
        context_score=context_score,
        entry_aligned=entry_aligned,
    )


async def select_setups(
    symbols: list[str],
    collector: MultiTimeframeCollector,
    context_cache: ContextCache,
    settings: SignalSettings,
    feature_engine: FeatureEngine | None = None,
) -> list[SignalSetup]:
    """Collect multi-TF data per symbol, score it, return passing setups (best first)."""
    engine = feature_engine or FeatureEngine()
    setups: list[SignalSetup] = []
    for symbol in symbols:
        try:
            mtf = await collector.collect(symbol)
            context = await context_cache.get(symbol)
        except Exception:
            logger.exception("failed to collect multi-timeframe data for %s", symbol)
            continue
        strategy = build_strategy(settings.strategy_name, symbol)
        setup = evaluate_symbol(symbol, mtf, context, strategy, settings, engine)
        if setup is not None:
            setups.append(setup)
    setups.sort(key=lambda s: s.quality, reverse=True)
    return setups
