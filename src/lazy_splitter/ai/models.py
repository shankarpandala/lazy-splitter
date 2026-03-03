"""AI-specific data models for the lazy-splitter AI module.

These dataclasses represent the results of AI-powered operations such as
LLM-based chapter detection, OCR text extraction, and text summarisation.
They are deliberately lightweight and serialisable so that they can be
passed between pipeline stages or persisted to JSON.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, List, Optional


@dataclasses.dataclass
class AIDetectionResult:
    """Result of an AI-powered chapter / section detection operation.

    Attributes
    ----------
    chapters:
        Detected chapter boundaries.  Each dictionary contains at least
        ``"title"`` (str), ``"start_index"`` (int), and ``"end_index"`` (int).
        Additional keys may be present depending on the detection method.
    method:
        Name of the detection method that produced this result
        (e.g. ``"llm"``, ``"topic"``, ``"semantic"``).
    model_used:
        Identifier of the model or algorithm used (e.g.
        ``"gpt-4"``, ``"nmf"``, ``"all-MiniLM-L6-v2"``).
    confidence:
        Overall confidence score in the range ``[0.0, 1.0]``.
    processing_time:
        Wall-clock time in seconds that the detection took.
    metadata:
        Arbitrary extra data for downstream consumers.
    """

    chapters: List[Dict[str, Any]]
    method: str
    model_used: str = ""
    confidence: float = 1.0
    processing_time: float = 0.0
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)

    # -- Properties ----------------------------------------------------------

    @property
    def chapter_count(self) -> int:
        """Number of detected chapters."""
        return len(self.chapters)

    # -- Serialisation -------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dictionary suitable for JSON encoding.

        Returns
        -------
        dict
            Dictionary representation of this result.
        """
        return {
            "chapters": list(self.chapters),
            "method": self.method,
            "model_used": self.model_used,
            "confidence": self.confidence,
            "processing_time": self.processing_time,
            "chapter_count": self.chapter_count,
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:
        return (
            f"AIDetectionResult(method={self.method!r}, "
            f"model={self.model_used!r}, "
            f"chapters={self.chapter_count}, "
            f"confidence={self.confidence:.2f}, "
            f"time={self.processing_time:.2f}s)"
        )


@dataclasses.dataclass
class OCRResult:
    """Result of an OCR text extraction operation.

    Attributes
    ----------
    text:
        The extracted plain text.
    confidence:
        Average OCR confidence score in the range ``[0.0, 1.0]``.
    language_detected:
        ISO 639-1 language code detected during OCR (e.g. ``"en"``),
        or an empty string if not available.
    engine_used:
        Name of the OCR engine that produced this result
        (e.g. ``"tesseract"``, ``"easyocr"``).
    metadata:
        Arbitrary extra data (page count, word count, etc.).
    """

    text: str
    confidence: float = 0.0
    language_detected: str = ""
    engine_used: str = ""
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)

    # -- Properties ----------------------------------------------------------

    @property
    def word_count(self) -> int:
        """Approximate word count of the extracted text."""
        return len(self.text.split()) if self.text else 0

    @property
    def is_empty(self) -> bool:
        """Return ``True`` if no meaningful text was extracted."""
        return len(self.text.strip()) == 0

    # -- Serialisation -------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dictionary suitable for JSON encoding.

        Returns
        -------
        dict
            Dictionary representation of this result.
        """
        return {
            "text": self.text,
            "confidence": self.confidence,
            "language_detected": self.language_detected,
            "engine_used": self.engine_used,
            "word_count": self.word_count,
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:
        preview = self.text[:60] + "..." if len(self.text) > 60 else self.text
        return (
            f"OCRResult(engine={self.engine_used!r}, "
            f"confidence={self.confidence:.2f}, "
            f"words={self.word_count}, "
            f"text={preview!r})"
        )


@dataclasses.dataclass
class SummaryResult:
    """Result of an LLM-based text summarisation.

    Attributes
    ----------
    summary:
        The generated summary text.
    title:
        A short generated title for the summarised section, or an empty
        string if title generation was not requested.
    word_count:
        Word count of the generated summary.
    model_used:
        Identifier of the LLM that produced the summary
        (e.g. ``"gpt-4"``, ``"claude-3-opus-20240229"``).
    metadata:
        Arbitrary extra data (token counts, latency, etc.).
    """

    summary: str
    title: str = ""
    word_count: int = 0
    model_used: str = ""
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        # Auto-compute word count from the summary if not explicitly set.
        if self.word_count == 0 and self.summary:
            self.word_count = len(self.summary.split())

    # -- Serialisation -------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dictionary suitable for JSON encoding.

        Returns
        -------
        dict
            Dictionary representation of this result.
        """
        return {
            "summary": self.summary,
            "title": self.title,
            "word_count": self.word_count,
            "model_used": self.model_used,
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:
        preview = self.summary[:60] + "..." if len(self.summary) > 60 else self.summary
        return (
            f"SummaryResult(model={self.model_used!r}, "
            f"words={self.word_count}, "
            f"title={self.title!r}, "
            f"summary={preview!r})"
        )
