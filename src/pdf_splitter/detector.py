"""Chapter detection logic for PDF files."""

import re
from pathlib import Path
from typing import Optional
import fitz  # PyMuPDF

from pdf_splitter.models import Chapter, DetectionResult


class ChapterDetector:
    """Detects chapters in PDF files using various strategies."""
    
    # Common chapter heading patterns
    CHAPTER_PATTERNS = [
        r'^Chapter\s+(\d+|[IVXLCDM]+)[\s:.-]*(.*?)$',
        r'^CHAPTER\s+(\d+|[IVXLCDM]+)[\s:.-]*(.*?)$',
        r'^(\d+)\.\s+(.+)$',  # Numbered headings like "1. Introduction"
        r'^Part\s+(\d+|[IVXLCDM]+)[\s:.-]*(.*?)$',
        r'^PART\s+(\d+|[IVXLCDM]+)[\s:.-]*(.*?)$',
    ]
    
    def __init__(self, sensitivity: str = "medium"):
        """
        Initialize the detector.
        
        Args:
            sensitivity: Detection sensitivity ('low', 'medium', 'high')
        """
        self.sensitivity = sensitivity
        self._set_thresholds()
    
    def _set_thresholds(self) -> None:
        """Set detection thresholds based on sensitivity."""
        thresholds = {
            "low": {"font_size_ratio": 1.5, "min_confidence": 0.8},
            "medium": {"font_size_ratio": 1.3, "min_confidence": 0.6},
            "high": {"font_size_ratio": 1.2, "min_confidence": 0.4},
        }
        config = thresholds.get(self.sensitivity, thresholds["medium"])
        self.font_size_ratio = config["font_size_ratio"]
        self.min_confidence = config["min_confidence"]
    
    def detect(
        self, 
        pdf_path: Path, 
        strategy: str = "hybrid",
        bookmark_level: int = 1
    ) -> DetectionResult:
        """
        Detect chapters in a PDF file.
        
        Args:
            pdf_path: Path to the PDF file
            strategy: Detection strategy ('bookmarks', 'heuristic', or 'hybrid')
            bookmark_level: Which bookmark level to use as chapters (1=top level, 2=sub-chapters, etc.)
        
        Returns:
            DetectionResult containing detected chapters
        """
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        has_bookmarks = len(doc.get_toc()) > 0
        
        chapters: list[Chapter] = []
        
        if strategy == "bookmarks" or (strategy == "hybrid" and has_bookmarks):
            chapters = self._detect_from_bookmarks(doc, bookmark_level)
            strategy_used = "bookmarks"
        
        if not chapters and strategy in ("heuristic", "hybrid"):
            chapters = self._detect_from_heuristics(doc)
            strategy_used = "heuristic"
        
        # If still no chapters found, treat entire document as one chapter
        if not chapters:
            chapters = [Chapter(
                title="Complete Document",
                start_page=1,
                end_page=total_pages,
                detection_method="fallback",
                confidence=1.0
            )]
            strategy_used = "fallback"
        else:
            strategy_used = strategy if chapters else "fallback"
        
        doc.close()
        
        return DetectionResult(
            chapters=chapters,
            strategy_used=strategy_used,
            total_pages=total_pages,
            has_bookmarks=has_bookmarks
        )
    
    def _detect_from_bookmarks(self, doc: fitz.Document, bookmark_level: int = 1) -> list[Chapter]:
        """
        Detect chapters from PDF bookmarks/outline.
        
        Args:
            doc: PyMuPDF document object
            bookmark_level: Which bookmark level to extract (1=top, 2=chapters, etc.)
        
        Returns:
            List of detected chapters
        """
        toc = doc.get_toc()
        if not toc:
            return []
        
        chapters: list[Chapter] = []
        total_pages = len(doc)
        
        # Filter for specified bookmark level
        top_level_items = [item for item in toc if item[0] == bookmark_level]
        
        for i, (level, title, page_num) in enumerate(top_level_items):
            start_page = page_num
            
            # Determine end page (start of next chapter or end of document)
            if i + 1 < len(top_level_items):
                end_page = top_level_items[i + 1][2] - 1
            else:
                end_page = total_pages
            
            if start_page <= end_page:
                chapters.append(Chapter(
                    title=title.strip(),
                    start_page=start_page,
                    end_page=end_page,
                    level=level,
                    detection_method="bookmark",
                    confidence=1.0
                ))
        
        return chapters
    
    def _detect_from_heuristics(self, doc: fitz.Document) -> list[Chapter]:
        """
        Detect chapters using text analysis heuristics.
        
        Args:
            doc: PyMuPDF document object
        
        Returns:
            List of detected chapters
        """
        chapters: list[Chapter] = []
        potential_chapters: list[tuple[int, str, float]] = []
        
        # Analyze each page for chapter headings
        for page_num in range(len(doc)):
            page = doc[page_num]
            blocks = page.get_text("dict")["blocks"]
            
            # Look for text blocks that might be chapter headings
            for block in blocks:
                if block.get("type") == 0:  # Text block
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            text = span.get("text", "").strip()
                            font_size = span.get("size", 0)
                            
                            if text and self._is_potential_heading(text, font_size, blocks):
                                confidence = self._calculate_confidence(text, font_size)
                                if confidence >= self.min_confidence:
                                    potential_chapters.append((
                                        page_num + 1,  # 1-indexed
                                        text,
                                        confidence
                                    ))
                                break
        
        # Convert potential chapters to Chapter objects
        total_pages = len(doc)
        for i, (page_num, title, confidence) in enumerate(potential_chapters):
            start_page = page_num
            
            # End page is start of next chapter or end of document
            if i + 1 < len(potential_chapters):
                end_page = potential_chapters[i + 1][0] - 1
            else:
                end_page = total_pages
            
            chapters.append(Chapter(
                title=title,
                start_page=start_page,
                end_page=end_page,
                detection_method="heuristic",
                confidence=confidence
            ))
        
        return chapters
    
    def _is_potential_heading(
        self, 
        text: str, 
        font_size: float, 
        all_blocks: list
    ) -> bool:
        """
        Determine if text is likely a chapter heading.
        
        Args:
            text: The text to analyze
            font_size: Font size of the text
            all_blocks: All text blocks on the page
        
        Returns:
            True if text is likely a heading
        """
        # Check for chapter patterns
        for pattern in self.CHAPTER_PATTERNS:
            if re.match(pattern, text, re.IGNORECASE):
                return True
        
        # Check if font size is significantly larger than body text
        avg_font_size = self._get_average_font_size(all_blocks)
        if avg_font_size > 0 and font_size >= avg_font_size * self.font_size_ratio:
            # Additional check: heading shouldn't be too long
            if len(text.split()) <= 10:
                return True
        
        return False
    
    def _calculate_confidence(self, text: str, font_size: float) -> float:
        """
        Calculate confidence score for a potential chapter heading.
        
        Args:
            text: The heading text
            font_size: Font size of the text
        
        Returns:
            Confidence score between 0.0 and 1.0
        """
        confidence = 0.5  # Base confidence
        
        # Boost confidence for explicit chapter patterns
        for pattern in self.CHAPTER_PATTERNS:
            if re.match(pattern, text, re.IGNORECASE):
                confidence += 0.4
                break
        
        # Boost for larger font sizes
        if font_size >= 16:
            confidence += 0.1
        elif font_size >= 14:
            confidence += 0.05
        
        # Reduce confidence for very long headings
        word_count = len(text.split())
        if word_count > 10:
            confidence -= 0.2
        elif word_count > 6:
            confidence -= 0.1
        
        return min(1.0, max(0.0, confidence))
    
    def _get_average_font_size(self, blocks: list) -> float:
        """
        Calculate average font size from text blocks.
        
        Args:
            blocks: List of text blocks from a page
        
        Returns:
            Average font size
        """
        sizes = []
        for block in blocks:
            if block.get("type") == 0:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        size = span.get("size", 0)
                        if size > 0:
                            sizes.append(size)
        
        return sum(sizes) / len(sizes) if sizes else 0
