from abc import ABC, abstractmethod
from app.models.order import Order
from app.models.execution_report import ExecutionReport


class ExecutionPort(ABC):
    @abstractmethod
    async def execute(self, order: Order) -> ExecutionReport:
        pass
