from __future__ import annotations
from abc import ABC, abstractmethod
from models import EarningsReport


class BaseExtractor(ABC):
    @abstractmethod
    def can_handle(self, cover_text: str) -> bool:
        """Return True if this extractor can parse the given PDF cover page."""
        ...

    @abstractmethod
    def extract(self, pdf_path: str) -> EarningsReport:
        """Extract a validated EarningsReport from the given PDF."""
        ...
