"""Document-specific data models for the document splitter module.

Provides dataclasses for representing document sections (headings, slides,
worksheets, row ranges, etc.) and high-level document metadata.  These models
are consumed by :class:`~lazy_splitter.document.detector.DocumentDetector` and
:class:`~lazy_splitter.document.splitter.DocumentSplitter`.
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class SectionType(Enum):
    """Enumeration of recognised section kinds across all document formats."""

    HEADING = "heading"
    SECTION = "section"
    SLIDE = "slide"
    SHEET = "sheet"
    ROW_RANGE = "row_range"
    ARRAY_ELEMENT = "array_element"
    CHAPTER = "chapter"


class FileType(Enum):
    """Supported document file types."""

    DOCX = "docx"
    PPTX = "pptx"
    XLSX = "xlsx"
    MARKDOWN = "markdown"
    LATEX = "latex"
    HTML = "html"
    CSV = "csv"
    JSON = "json"
    XML = "xml"
    UNKNOWN = "unknown"


# Mapping from common extensions to FileType.
_EXTENSION_MAP: Dict[str, FileType] = {
    ".docx": FileType.DOCX,
    ".pptx": FileType.PPTX,
    ".xlsx": FileType.XLSX,
    ".md": FileType.MARKDOWN,
    ".markdown": FileType.MARKDOWN,
    ".tex": FileType.LATEX,
    ".latex": FileType.LATEX,
    ".html": FileType.HTML,
    ".htm": FileType.HTML,
    ".csv": FileType.CSV,
    ".tsv": FileType.CSV,
    ".json": FileType.JSON,
    ".xml": FileType.XML,
}


def file_type_from_path(path: Path) -> FileType:
    """Determine the :class:`FileType` of *path* from its extension.

    Parameters
    ----------
    path:
        File path whose suffix is inspected (case-insensitive).

    Returns
    -------
    FileType
        The matching file type, or :attr:`FileType.UNKNOWN` when the
        extension is not recognised.
    """
    return _EXTENSION_MAP.get(path.suffix.lower(), FileType.UNKNOWN)


@dataclasses.dataclass
class DocumentSection:
    """A single detected section within a document.

    Attributes
    ----------
    title:
        Human-readable name for the section (e.g. heading text, sheet name,
        slide title, ``"Rows 1-100"``).
    start_index:
        Zero-based start position.  Interpretation depends on
        *section_type* (character offset, row number, slide index, etc.).
    end_index:
        Zero-based *exclusive* end position.
    level:
        Nesting depth of the section (1 = top-level).
    section_type:
        The kind of section this represents.
    detection_method:
        Name of the strategy / heuristic that produced this section.
    confidence:
        Confidence score in the range ``[0.0, 1.0]``.
    content_preview:
        Optional short preview of the section's textual content.
    metadata:
        Arbitrary extra data attached by the detector.
    """

    title: str
    start_index: int
    end_index: int
    level: int = 1
    section_type: SectionType = SectionType.SECTION
    detection_method: str = "auto"
    confidence: float = 1.0
    content_preview: str = ""
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)

    @property
    def span(self) -> int:
        """Number of units (characters, rows, slides, ...) covered."""
        return max(0, self.end_index - self.start_index)

    def __repr__(self) -> str:
        return (
            f"DocumentSection(title={self.title!r}, "
            f"[{self.start_index}:{self.end_index}], "
            f"type={self.section_type.value}, level={self.level})"
        )


@dataclasses.dataclass
class DocumentInfo:
    """High-level metadata about a document file.

    Attributes
    ----------
    path:
        Absolute or relative path to the file.
    file_type:
        Detected file type.
    page_count:
        Total number of pages (or slides / sheets) if applicable.
    section_count:
        Number of detected sections.
    word_count:
        Approximate word count of the document's textual content.
    has_images:
        Whether the document contains embedded images.
    has_tables:
        Whether the document contains tables.
    metadata:
        Arbitrary extra metadata (e.g. author, title, creation date).
    """

    path: Path
    file_type: FileType
    page_count: Optional[int] = None
    section_count: int = 0
    word_count: int = 0
    has_images: bool = False
    has_tables: bool = False
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"DocumentInfo(path={self.path!r}, type={self.file_type.value}, "
            f"sections={self.section_count}, words={self.word_count})"
        )
