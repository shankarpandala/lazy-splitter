"""
Example script showing how to use pdf-splitter programmatically.
"""

from pathlib import Path
from pdf_splitter.detector import ChapterDetector
from pdf_splitter.splitter import PDFSplitter


def example_basic_usage():
    """Basic usage example."""
    # Path to your PDF
    pdf_path = Path("example.pdf")
    
    # Detect chapters
    detector = ChapterDetector(sensitivity="medium")
    result = detector.detect(pdf_path, strategy="hybrid")
    
    # Print results
    print(f"Found {result.chapter_count} chapters:")
    for i, chapter in enumerate(result.chapters, 1):
        print(f"  {i}. {chapter.title} (pages {chapter.start_page}-{chapter.end_page})")
    
    # Split PDF
    output_dir = Path("output")
    splitter = PDFSplitter(output_dir)
    files = splitter.split(pdf_path, result.chapters)
    
    print(f"\nCreated {len(files)} files in {output_dir}/")


def example_bookmarks_only():
    """Use bookmarks strategy only."""
    pdf_path = Path("example.pdf")
    
    detector = ChapterDetector()
    result = detector.detect(pdf_path, strategy="bookmarks")
    
    if result.has_bookmarks:
        print(f"PDF has bookmarks! Found {result.chapter_count} chapters")
    else:
        print("PDF has no bookmarks, try heuristic strategy")


def example_custom_pattern():
    """Use custom filename pattern."""
    pdf_path = Path("example.pdf")
    
    detector = ChapterDetector()
    result = detector.detect(pdf_path)
    
    # Custom pattern: "Chapter_01.pdf", "Chapter_02.pdf", etc.
    splitter = PDFSplitter(
        output_dir=Path("output"),
        filename_pattern="Chapter_{index:02d}.pdf"
    )
    
    files = splitter.split(pdf_path, result.chapters)
    print(f"Created: {[f.name for f in files]}")


def example_high_sensitivity():
    """Use high sensitivity for more aggressive detection."""
    pdf_path = Path("example.pdf")
    
    # High sensitivity detects more potential chapters
    detector = ChapterDetector(sensitivity="high")
    result = detector.detect(pdf_path, strategy="heuristic")
    
    # Filter by confidence if needed
    high_confidence_chapters = [
        ch for ch in result.chapters 
        if ch.confidence >= 0.7
    ]
    
    print(f"Total detected: {len(result.chapters)}")
    print(f"High confidence: {len(high_confidence_chapters)}")


if __name__ == "__main__":
    # Uncomment the example you want to run:
    
    # example_basic_usage()
    # example_bookmarks_only()
    # example_custom_pattern()
    # example_high_sensitivity()
    
    print("Uncomment an example function to run it!")
