from abc import ABC, abstractmethod
from app.models.feature_vector import FeatureVector


class StrategyPort(ABC):
    @abstractmethod
    def generate_signal(self, features: FeatureVector):
        pass
