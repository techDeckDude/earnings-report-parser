from __future__ import annotations
from abc import ABC, abstractmethod
from models import EarningsReport


class BaseExtractor(ABC):
    @abstractmethod
    def can_handle(self, file_path: str) -> bool:
        """Return True if this extractor can parse the file at the given path."""
        ...

    @abstractmethod
    def extract(self, file_path: str) -> EarningsReport:
        """Extract a validated EarningsReport from the given file."""
        ...
