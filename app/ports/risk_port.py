from abc import ABC, abstractmethod
from app.models.trade_candidate import TradeCandidate
from app.models.risk_decision import RiskDecision


class RiskPort(ABC):
    @abstractmethod
    def evaluate(self, trade: TradeCandidate) -> RiskDecision:
        pass
