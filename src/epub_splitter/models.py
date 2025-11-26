"""Data models for EPUB chapter detection and splitting."""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class EpubChapter:
    """Represents a chapter in an EPUB file."""

    title: str
    file_path: str  # Path to XHTML file within EPUB
    html_id: Optional[str] = None  # Anchor ID if chapter is within file
    level: int = 1  # Hierarchy level (1 = top-level, 2 = subsection, etc.)
    detection_method: str = "unknown"  # How this chapter was detected
    confidence: float = 1.0  # Confidence score (0.0 to 1.0)
    content_length: int = 0  # Character count of chapter content

    @property
    def location(self) -> str:
        """Get the full location reference."""
        if self.html_id:
            return f"{self.file_path}#{self.html_id}"
        return self.file_path


@dataclass
class EpubDetectionResult:
    """Result of chapter detection in an EPUB file."""

    chapters: List[EpubChapter]
    strategy_used: str
    total_files: int  # Number of content files in EPUB
    has_toc: bool  # Whether EPUB has a table of contents

    @property
    def chapter_count(self) -> int:
        """Get the number of detected chapters."""
        return len(self.chapters)

    def get_chapters_by_level(self, level: int) -> List[EpubChapter]:
        """Filter chapters by hierarchy level."""
        return [ch for ch in self.chapters if ch.level == level]
