from abc import ABC, abstractmethod
from typing import List
from app.models.company import Company
from app.schemas.signal import SignalCreate

class BaseCollector(ABC):
    collector_type: str

    @abstractmethod
    def collect(self, company: Company) -> List[SignalCreate]:
        """
        Extract signals from a company and return a list of SignalCreate objects.
        """
        pass
