"""Document splitting module for lazy-splitter.

Supports DOCX, PPTX, XLSX, Markdown, LaTeX, HTML, CSV, JSON, and XML files.

Quick start::

    from lazy_splitter.document import DocumentDetector, DocumentSplitter

    detector = DocumentDetector()
    result = detector.detect(Path("report.docx"))

    splitter = DocumentSplitter()
    split_result = splitter.split(Path("report.docx"), result.segments)
"""

from __future__ import annotations

from lazy_splitter.document.detector import DocumentDetector
from lazy_splitter.document.models import (
    DocumentInfo,
    DocumentSection,
    FileType,
    SectionType,
    file_type_from_path,
)
from lazy_splitter.document.splitter import DocumentSplitter

__all__ = [
    # Core classes
    "DocumentDetector",
    "DocumentSplitter",
    # Models
    "DocumentInfo",
    "DocumentSection",
    "FileType",
    "SectionType",
    # Utilities
    "file_type_from_path",
]
