"""EPUB splitting module - re-exports from epub_splitter for unified access."""
from __future__ import annotations

from epub_splitter.detector import EpubChapterDetector as EpubDetector
from epub_splitter.splitter import EpubSplitter
from epub_splitter.models import EpubChapter, EpubDetectionResult

__all__ = [
    "EpubDetector",
    "EpubSplitter",
    "EpubChapter",
    "EpubDetectionResult",
]
