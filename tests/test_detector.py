"""Unit tests for chapter detection."""

import pytest
from pathlib import Path
from pdf_splitter.detector import ChapterDetector
from pdf_splitter.models import Chapter, DetectionResult


class TestChapterDetector:
    """Test cases for ChapterDetector class."""
    
    def test_detector_initialization(self):
        """Test detector initializes with correct sensitivity settings."""
        detector_low = ChapterDetector(sensitivity="low")
        assert detector_low.font_size_ratio == 1.5
        assert detector_low.min_confidence == 0.8
        
        detector_medium = ChapterDetector(sensitivity="medium")
        assert detector_medium.font_size_ratio == 1.3
        assert detector_medium.min_confidence == 0.6
        
        detector_high = ChapterDetector(sensitivity="high")
        assert detector_high.font_size_ratio == 1.2
        assert detector_high.min_confidence == 0.4
    
    def test_sanitize_filename(self):
        """Test filename sanitization."""
        from pdf_splitter.splitter import PDFSplitter
        
        # Test invalid characters removal
        result = PDFSplitter._sanitize_filename("Chapter 1: Introduction/Overview")
        assert "/" not in result
        assert ":" not in result
        
        # Test space replacement
        result = PDFSplitter._sanitize_filename("Chapter   1   Introduction")
        assert "   " not in result
        assert "_" in result
        
        # Test truncation
        long_title = "A" * 150
        result = PDFSplitter._sanitize_filename(long_title, max_length=100)
        assert len(result) <= 100
        
        # Test empty string handling
        result = PDFSplitter._sanitize_filename("")
        assert result == "untitled"
    
    def test_calculate_confidence(self):
        """Test confidence calculation for chapter headings."""
        detector = ChapterDetector()
        
        # High confidence for explicit chapter pattern
        confidence = detector._calculate_confidence("Chapter 1: Introduction", 16)
        assert confidence >= 0.8
        
        # Lower confidence for non-chapter text
        confidence = detector._calculate_confidence("Some regular paragraph text here", 12)
        assert confidence < 0.8


# Fixtures for integration tests (would require actual PDF files)
@pytest.fixture
def sample_pdf_path():
    """Fixture providing path to a sample PDF (mock for now)."""
    # In real tests, this would point to actual test PDFs
    return Path("tests/fixtures/sample.pdf")


class TestIntegration:
    """Integration tests (require actual PDF files)."""
    
    @pytest.mark.skip(reason="Requires actual PDF file")
    def test_full_detection_and_split_workflow(self, sample_pdf_path, tmp_path):
        """Test complete workflow from detection to splitting."""
        detector = ChapterDetector()
        result = detector.detect(sample_pdf_path, strategy="hybrid")
        
        assert isinstance(result, DetectionResult)
        assert result.chapter_count > 0
        
        from pdf_splitter.splitter import PDFSplitter
        splitter = PDFSplitter(tmp_path)
        created_files = splitter.split(sample_pdf_path, result.chapters)
        
        assert len(created_files) == result.chapter_count
        for file_path in created_files:
            assert file_path.exists()
            assert file_path.suffix == ".pdf"
