from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.feature_vector import FeatureVector
from app.models.market_bundle import MarketBundle


class AnalyticsPort(ABC):
    @abstractmethod
    def build_features(self, market_data: MarketBundle) -> FeatureVector:
        pass
