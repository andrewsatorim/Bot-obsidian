from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.feature_vector import FeatureVector
from app.models.market_data_bundle import MarketDataBundle


class AnalyticsPort(ABC):
    @abstractmethod
    def build_features(self, market_data: MarketDataBundle) -> FeatureVector:
        pass
