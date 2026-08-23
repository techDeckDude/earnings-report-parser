from __future__ import annotations
from .base import BaseExtractor
from .palantir import PalantirExtractor
from .marvell import MarvellExtractor

_REGISTRY: list[BaseExtractor] = [
    PalantirExtractor(),
    MarvellExtractor(),
]


def get_extractor(file_path: str) -> BaseExtractor:
    """Return the first registered extractor that can handle the given file."""
    for extractor in _REGISTRY:
        if extractor.can_handle(file_path):
            return extractor
    raise ValueError(
        f"No registered extractor can handle: {file_path!r}\n"
        f"Registered extractors: {[type(e).__name__ for e in _REGISTRY]}"
    )
