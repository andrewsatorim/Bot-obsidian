from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.models.feature_vector import FeatureVector
from app.models.signal import Signal


class StrategyPort(ABC):
    @abstractmethod
    def generate_signal(self, features: FeatureVector) -> Optional[Signal]:
        pass
