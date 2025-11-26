"""Models for representing chapters and detection results."""

from dataclasses import dataclass
from typing import List


@dataclass
class Chapter:
    """Represents a detected chapter in a PDF."""

    title: str
    start_page: int
    end_page: int
    level: int = 1  # Hierarchy level (1 for main chapters, 2 for sections, etc.)
    detection_method: str = "unknown"  # 'bookmark', 'heuristic', or 'hybrid'
    confidence: float = 1.0  # Confidence score (0.0 to 1.0)

    @property
    def page_count(self) -> int:
        """Return the number of pages in this chapter."""
        return self.end_page - self.start_page + 1

    def __str__(self) -> str:
        """Return a human-readable string representation."""
        return f"{self.title} (pages {self.start_page}-{self.end_page})"


@dataclass
class DetectionResult:
    """Container for chapter detection results."""

    chapters: List[Chapter]
    strategy_used: str
    total_pages: int
    has_bookmarks: bool

    @property
    def chapter_count(self) -> int:
        """Return the number of detected chapters."""
        return len(self.chapters)

    def get_summary(self) -> str:
        """Return a summary of the detection results."""
        lines = [
            f"Detection Strategy: {self.strategy_used}",
            f"Total Pages: {self.total_pages}",
            f"Chapters Found: {self.chapter_count}",
            f"Has Bookmarks: {'Yes' if self.has_bookmarks else 'No'}",
        ]
        return "\n".join(lines)
