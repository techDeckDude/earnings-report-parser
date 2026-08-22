from __future__ import annotations
import pdfplumber
from .base import BaseExtractor
from .palantir import PalantirExtractor

_REGISTRY: list[BaseExtractor] = [
    PalantirExtractor(),
]


def get_extractor(pdf_path: str) -> BaseExtractor:
    """Read the PDF cover page and return the first registered extractor that can handle it."""
    with pdfplumber.open(pdf_path) as pdf:
        cover = pdf.pages[0].extract_text() or ""
    for extractor in _REGISTRY:
        if extractor.can_handle(cover):
            return extractor
    raise ValueError(
        f"No registered extractor can handle this PDF.\n"
        f"Cover text (first 300 chars):\n{cover[:300]}"
    )
