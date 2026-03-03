"""PDF splitting module - re-exports from pdf_splitter for unified access."""
from __future__ import annotations

from pdf_splitter.detector import ChapterDetector as PDFDetector
from pdf_splitter.splitter import PDFSplitter
from pdf_splitter.models import Chapter as PDFChapter, DetectionResult as PDFDetectionResult

__all__ = [
    "PDFDetector",
    "PDFSplitter",
    "PDFChapter",
    "PDFDetectionResult",
]
