from __future__ import annotations

import logging
import time
from typing import Optional

from app.models.enums import Direction
from app.models.feature_vector import FeatureVector
from app.models.signal import Signal
from app.ports.strategy_port import StrategyPort

logger = logging.getLogger(__name__)


class StrategyFusion(StrategyPort):
    """Combines signals from multiple strategies with configurable weights.

    A fused signal is emitted only when strategies agree on direction.
    The fused strength is a weighted average.
    """

    def __init__(
        self,
        strategies: list[tuple[StrategyPort, float]],
        min_agreement: int = 2,
        min_strength: float = 0.3,
    ) -> None:
        self._strategies = strategies  # (strategy, weight)
        self._min_agreement = min_agreement
        self._min_strength = min_strength

    def generate_signal(self, features: FeatureVector) -> Optional[Signal]:
        signals: list[tuple[Signal, float]] = []

        for strategy, weight in self._strategies:
            sig = strategy.generate_signal(features)
            if sig is not None:
                signals.append((sig, weight))

        if len(signals) < self._min_agreement:
            return None

        # Count direction votes
        long_weight = sum(w for s, w in signals if s.direction == Direction.LONG)
        short_weight = sum(w for s, w in signals if s.direction == Direction.SHORT)

        if long_weight > short_weight:
            direction = Direction.LONG
            agreeing = [(s, w) for s, w in signals if s.direction == Direction.LONG]
        elif short_weight > long_weight:
            direction = Direction.SHORT
            agreeing = [(s, w) for s, w in signals if s.direction == Direction.SHORT]
        else:
            return None  # Tie — no signal

        if len(agreeing) < self._min_agreement:
            return None

        # Weighted average strength
        total_weight = sum(w for _, w in agreeing)
        fused_strength = sum(s.strength * w for s, w in agreeing) / total_weight if total_weight > 0 else 0.0

        if fused_strength < self._min_strength:
            return None

        symbol = agreeing[0][0].symbol

        signal = Signal(
            symbol=symbol,
            direction=direction,
            strength=min(fused_strength, 1.0),
            timestamp=int(time.time()),
        )
        logger.info(
            "fused signal: %s strength=%.2f (%d/%d strategies agree)",
            direction.value, signal.strength, len(agreeing), len(self._strategies),
        )
        return signal
