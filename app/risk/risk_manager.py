from __future__ import annotations

import logging

from app.config import Settings
from app.models.risk_decision import RiskDecision
from app.models.trade_candidate import TradeCandidate
from app.ports.risk_port import RiskPort

logger = logging.getLogger(__name__)


class RiskManager(RiskPort):
    """ATR-based risk manager with portfolio-level controls."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.daily_pnl: float = 0.0
        self.open_positions: int = 0

    def evaluate(self, trade: TradeCandidate) -> RiskDecision:
        equity = self.settings.account_equity

        # Daily loss limit
        max_loss = equity * self.settings.max_daily_loss_pct
        if self.daily_pnl < -max_loss:
            return RiskDecision(
                allow_trade=False,
                risk_multiplier=1.0,
                reason=f"daily loss limit hit: pnl={self.daily_pnl:.2f} limit=-{max_loss:.2f}",
            )

        # Max open positions
        if self.open_positions >= self.settings.max_open_positions:
            return RiskDecision(
                allow_trade=False,
                risk_multiplier=1.0,
                reason=f"max open positions reached: {self.open_positions}",
            )

        # Minimum confidence
        if trade.confidence < self.settings.min_confidence:
            return RiskDecision(
                allow_trade=False,
                risk_multiplier=1.0,
                reason=f"confidence too low: {trade.confidence:.2f} < {self.settings.min_confidence:.2f}",
            )

        # Compute risk multiplier
        risk_multiplier = min(trade.risk_multiplier * trade.confidence, 3.0)
        risk_multiplier = max(risk_multiplier, 0.1)

        logger.info("trade approved: %s %s confidence=%.2f multiplier=%.2f", trade.symbol, trade.direction.value, trade.confidence, risk_multiplier)

        return RiskDecision(
            allow_trade=True,
            risk_multiplier=risk_multiplier,
            reason="approved",
        )

    def record_pnl(self, pnl: float) -> None:
        self.daily_pnl += pnl

    def reset_daily(self) -> None:
        self.daily_pnl = 0.0
