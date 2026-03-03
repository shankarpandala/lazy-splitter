"""Shared data models for lazy-splitter.

All models are plain :mod:`dataclasses` with no heavyweight dependencies so
they can be imported freely from any sub-package.  They are the canonical
representation exchanged between detectors, splitters, mergers, and converters.

Each model is deliberately *format-agnostic* at this layer; format-specific
sub-packages may extend them via composition or additional metadata dicts.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Chapter / segment models (one per supported media family)
# ---------------------------------------------------------------------------

@dataclass
class Chapter:
    """A detected chapter within a page-oriented document (PDF, DJVU, etc.).

    Attributes:
        title: Human-readable chapter title.
        start_page: First page of the chapter (1-indexed).
        end_page: Last page of the chapter (inclusive, 1-indexed).
        level: Hierarchy depth (1 = top-level chapter, 2 = sub-section, ...).
        detection_method: How this chapter was detected (e.g. ``"bookmark"``,
            ``"heuristic"``, ``"hybrid"``).
        confidence: Confidence score in the range ``[0.0, 1.0]``.
        metadata: Arbitrary extra data for downstream consumers.
    """

    title: str
    start_page: int
    end_page: int
    level: int = 1
    detection_method: str = "unknown"
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def page_count(self) -> int:
        """Return the number of pages spanned by this chapter."""
        return self.end_page - self.start_page + 1

    def __str__(self) -> str:
        return f"{self.title} (pages {self.start_page}-{self.end_page})"


@dataclass
class EpubChapter:
    """A detected chapter within an EPUB file.

    Attributes:
        title: Human-readable chapter title.
        file_path: Path to the XHTML content file inside the EPUB archive.
        html_id: Optional anchor id when the chapter starts mid-file.
        level: Hierarchy depth (1 = top-level chapter).
        detection_method: Detection strategy that found this chapter.
        confidence: Confidence score in ``[0.0, 1.0]``.
        content_length: Approximate character count of the chapter body.
    """

    title: str
    file_path: str
    html_id: Optional[str] = None
    level: int = 1
    detection_method: str = "unknown"
    confidence: float = 1.0
    content_length: int = 0

    @property
    def location(self) -> str:
        """Full location reference including optional fragment."""
        if self.html_id:
            return f"{self.file_path}#{self.html_id}"
        return self.file_path

    def __str__(self) -> str:
        return f"{self.title} ({self.location})"


@dataclass
class VideoSegment:
    """A detected segment within a video file.

    Attributes:
        title: Human-readable segment title.
        start_time: Start offset in seconds from the beginning.
        end_time: End offset in seconds from the beginning.
        detection_method: Strategy that found this segment.
        confidence: Confidence score in ``[0.0, 1.0]``.
        thumbnail_path: Optional path to a representative thumbnail image.
    """

    title: str
    start_time: float
    end_time: float
    detection_method: str = "unknown"
    confidence: float = 1.0
    thumbnail_path: Optional[str] = None

    @property
    def duration(self) -> float:
        """Duration of the segment in seconds."""
        return self.end_time - self.start_time

    def __str__(self) -> str:
        return f"{self.title} ({self.start_time:.1f}s - {self.end_time:.1f}s)"


@dataclass
class AudioSegment:
    """A detected segment within an audio file.

    Attributes:
        title: Human-readable segment title.
        start_time: Start offset in seconds.
        end_time: End offset in seconds.
        detection_method: Strategy used for detection.
        confidence: Confidence score in ``[0.0, 1.0]``.
        metadata: Extra data (e.g. bitrate, codec, embedded artwork path).
    """

    title: str
    start_time: float
    end_time: float
    detection_method: str = "unknown"
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        """Duration of the segment in seconds."""
        return self.end_time - self.start_time

    def __str__(self) -> str:
        return f"{self.title} ({self.start_time:.1f}s - {self.end_time:.1f}s)"


@dataclass
class DocumentSection:
    """A detected section within a structured document (DOCX, HTML, Markdown, etc.).

    Attributes:
        title: Section heading text.
        start_index: Start position (meaning varies by format; may be a
            character offset, paragraph index, or similar).
        end_index: End position (exclusive).
        level: Heading level (1 = ``<h1>`` / top-level, etc.).
        section_type: Semantic type (e.g. ``"heading"``, ``"list"``, ``"table"``).
        detection_method: How this section was identified.
        confidence: Confidence score in ``[0.0, 1.0]``.
    """

    title: str
    start_index: int
    end_index: int
    level: int = 1
    section_type: str = "heading"
    detection_method: str = "unknown"
    confidence: float = 1.0

    @property
    def length(self) -> int:
        """Length of the section (end_index - start_index)."""
        return self.end_index - self.start_index

    def __str__(self) -> str:
        return f"{self.title} (index {self.start_index}-{self.end_index})"


@dataclass
class ImageFrame:
    """Metadata for a single image frame (TIFF pages, GIF frames, sprite sheets, etc.).

    Attributes:
        title: Label for the frame.
        index: Zero-based frame index.
        width: Frame width in pixels.
        height: Frame height in pixels.
        format: Image format / codec (e.g. ``"PNG"``, ``"JPEG"``).
        metadata: Arbitrary extra data (EXIF, ICC profile info, etc.).
    """

    title: str
    index: int
    width: int
    height: int
    format: str = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def resolution(self) -> str:
        """Human-readable resolution string."""
        return f"{self.width}x{self.height}"

    def __str__(self) -> str:
        return f"{self.title} (frame {self.index}, {self.resolution})"


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

@dataclass
class DetectionResult:
    """Aggregated result returned by any detector.

    The *chapters* list holds instances of whichever chapter / segment model
    is appropriate for the file type being analysed (e.g. :class:`Chapter` for
    PDFs, :class:`VideoSegment` for videos).

    Attributes:
        chapters: Detected items.
        strategy_used: Name of the strategy that produced these results.
        total_items: Total countable items in the source (pages, files, frames, ...).
        metadata: Arbitrary extra data.
        source_path: Path to the file that was analysed.
        file_type: Detected / declared file type (e.g. ``"pdf"``, ``"epub"``).
    """

    chapters: List[Any]
    strategy_used: str
    total_items: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_path: Optional[str] = None
    file_type: Optional[str] = None

    # -- Properties ----------------------------------------------------------

    @property
    def chapter_count(self) -> int:
        """Number of detected chapters / segments."""
        return len(self.chapters)

    # -- Public methods ------------------------------------------------------

    def get_summary(self) -> str:
        """Return a human-readable multi-line summary.

        Returns:
            Formatted summary string including strategy, counts, and source
            information.
        """
        lines = [
            f"Detection Strategy: {self.strategy_used}",
            f"Total Items: {self.total_items}",
            f"Chapters Found: {self.chapter_count}",
        ]
        if self.source_path:
            lines.append(f"Source: {self.source_path}")
        if self.file_type:
            lines.append(f"File Type: {self.file_type}")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dictionary.

        Chapters are serialised via their ``__dict__`` when they are dataclass
        instances; otherwise they are included as-is.

        Returns:
            Dictionary representation suitable for JSON encoding.
        """

        def _chapter_to_dict(ch: Any) -> Any:
            if hasattr(ch, "__dataclass_fields__"):
                return dict(ch.__dict__)
            return ch  # pragma: no cover

        return {
            "chapters": [_chapter_to_dict(c) for c in self.chapters],
            "strategy_used": self.strategy_used,
            "total_items": self.total_items,
            "chapter_count": self.chapter_count,
            "metadata": self.metadata,
            "source_path": self.source_path,
            "file_type": self.file_type,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialise to a JSON string.

        Parameters:
            indent: Number of spaces for pretty-printing.  Use ``0`` or
                *None* for compact output.

        Returns:
            JSON-encoded string.
        """
        return json.dumps(self.to_dict(), indent=indent, default=str)


@dataclass
class SplitResult:
    """Result returned after a split operation.

    Attributes:
        created_files: List of paths to the files that were created.
        source_path: Path to the original input file.
        duration_seconds: Wall-clock time the operation took.
        warnings: Non-fatal issues encountered during splitting.
        errors: Fatal errors encountered (if partial results were still produced).
        metadata: Arbitrary extra data.
    """

    created_files: List[Path]
    source_path: Optional[str] = None
    duration_seconds: float = 0.0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # -- Properties ----------------------------------------------------------

    @property
    def success(self) -> bool:
        """Whether the split completed without errors."""
        return len(self.errors) == 0

    @property
    def file_count(self) -> int:
        """Number of files that were created."""
        return len(self.created_files)

    @property
    def total_size(self) -> int:
        """Combined size (in bytes) of all created files.

        Files that no longer exist on disk are silently skipped.
        """
        total = 0
        for fp in self.created_files:
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
        return total

    # -- Public methods ------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dictionary.

        Returns:
            Dictionary representation suitable for JSON encoding.
        """
        return {
            "created_files": [str(p) for p in self.created_files],
            "source_path": self.source_path,
            "duration_seconds": self.duration_seconds,
            "file_count": self.file_count,
            "total_size": self.total_size,
            "success": self.success,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "metadata": self.metadata,
        }


@dataclass
class MergeResult:
    """Result returned after a merge operation.

    Attributes:
        output_path: Path to the merged output file.
        source_paths: Paths to the input files that were merged.
        duration_seconds: Wall-clock time the operation took.
        metadata: Arbitrary extra data.
    """

    output_path: Path
    source_paths: List[Path] = field(default_factory=list)
    duration_seconds: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dictionary.

        Returns:
            Dictionary representation suitable for JSON encoding.
        """
        return {
            "output_path": str(self.output_path),
            "source_paths": [str(p) for p in self.source_paths],
            "duration_seconds": self.duration_seconds,
            "metadata": self.metadata,
        }


@dataclass
class ConversionResult:
    """Result returned after a format conversion.

    Attributes:
        input_path: Path to the original file.
        output_path: Path to the converted file.
        input_format: Source format identifier (e.g. ``"pdf"``).
        output_format: Target format identifier (e.g. ``"epub"``).
        duration_seconds: Wall-clock time the operation took.
        metadata: Arbitrary extra data.
    """

    input_path: Path
    output_path: Path
    input_format: str = ""
    output_format: str = ""
    duration_seconds: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dictionary.

        Returns:
            Dictionary representation suitable for JSON encoding.
        """
        return {
            "input_path": str(self.input_path),
            "output_path": str(self.output_path),
            "input_format": self.input_format,
            "output_format": self.output_format,
            "duration_seconds": self.duration_seconds,
            "metadata": self.metadata,
        }
