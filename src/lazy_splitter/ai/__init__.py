"""AI/ML-powered features for lazy-splitter.

This package provides AI and machine-learning capabilities including:

* :class:`AIDetector` -- LLM, topic-modelling, and semantic-similarity based
  chapter detection.
* :class:`OCREngine` -- OCR text extraction via Tesseract or EasyOCR.
* :class:`ChapterSummarizer` -- LLM-powered text summarisation and title
  generation.
* :class:`SpeechDetector` -- Speech-to-text transcription and chapter
  detection from audio.
* :class:`AIDetectionResult`, :class:`OCRResult`, :class:`SummaryResult` --
  Data models for AI operation results.

All heavy dependencies are imported lazily so that importing this package
has near-zero cost when the optional ML libraries are not installed.
"""

from __future__ import annotations

__all__ = [
    # Classes
    "AIDetector",
    "ChapterSummarizer",
    "OCREngine",
    "SpeechDetector",
    # Models
    "AIDetectionResult",
    "OCRResult",
    "SummaryResult",
]


def __getattr__(name: str) -> object:
    """Lazy-load public classes to avoid importing heavy dependencies at
    package import time.
    """
    if name == "AIDetector":
        from lazy_splitter.ai.detector import AIDetector
        return AIDetector
    if name == "OCREngine":
        from lazy_splitter.ai.ocr import OCREngine
        return OCREngine
    if name == "ChapterSummarizer":
        from lazy_splitter.ai.summarizer import ChapterSummarizer
        return ChapterSummarizer
    if name == "SpeechDetector":
        from lazy_splitter.ai.speech import SpeechDetector
        return SpeechDetector
    if name == "AIDetectionResult":
        from lazy_splitter.ai.models import AIDetectionResult
        return AIDetectionResult
    if name == "OCRResult":
        from lazy_splitter.ai.models import OCRResult
        return OCRResult
    if name == "SummaryResult":
        from lazy_splitter.ai.models import SummaryResult
        return SummaryResult
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
