from abc import ABC, abstractmethod
from app.models.feature_vector import FeatureVector


class AnalyticsPort(ABC):
    @abstractmethod
    def build_features(self, market_data) -> FeatureVector:
        pass
