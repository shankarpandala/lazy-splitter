"""PDF splitting functionality."""

from pathlib import Path
import fitz  # PyMuPDF

from pdf_splitter.models import Chapter


class PDFSplitter:
    """Handles splitting PDF files by chapters."""
    
    def __init__(self, output_dir: Path, filename_pattern: str = "{index:02d}_{title}.pdf"):
        """
        Initialize the splitter.
        
        Args:
            output_dir: Directory where split PDFs will be saved
            filename_pattern: Pattern for output filenames. Available placeholders:
                - {index}: Chapter index (starts at 1)
                - {title}: Chapter title (sanitized)
                - {start}: Start page number
                - {end}: End page number
                - {pages}: Number of pages in chapter
        """
        self.output_dir = Path(output_dir)
        self.filename_pattern = filename_pattern
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def split(
        self, 
        pdf_path: Path, 
        chapters: list[Chapter],
        preserve_metadata: bool = True
    ) -> list[Path]:
        """
        Split a PDF file into separate files by chapters.
        
        Args:
            pdf_path: Path to the source PDF file
            chapters: List of chapters to split by
            preserve_metadata: Whether to preserve PDF metadata in split files
        
        Returns:
            List of paths to the created PDF files
        """
        doc = fitz.open(pdf_path)
        created_files: list[Path] = []
        
        # Get original metadata
        metadata = doc.metadata if preserve_metadata else {}
        
        for index, chapter in enumerate(chapters, start=1):
            output_path = self._generate_filename(chapter, index)
            
            # Create new PDF with chapter pages
            new_doc = fitz.open()
            
            # Insert pages (PyMuPDF uses 0-based indexing)
            new_doc.insert_pdf(
                doc,
                from_page=chapter.start_page - 1,
                to_page=chapter.end_page - 1
            )
            
            # Set metadata
            if preserve_metadata:
                new_doc.set_metadata(metadata)
                # Add chapter-specific title
                new_doc.set_metadata({"title": chapter.title})
            
            # Save the new PDF
            new_doc.save(output_path)
            new_doc.close()
            
            created_files.append(output_path)
        
        doc.close()
        return created_files
    
    def _generate_filename(self, chapter: Chapter, index: int) -> Path:
        """
        Generate output filename based on pattern and chapter info.
        
        Args:
            chapter: Chapter object
            index: Chapter index (1-based)
        
        Returns:
            Path to the output file
        """
        # Sanitize chapter title for filename
        safe_title = self._sanitize_filename(chapter.title)
        
        # Format filename using pattern
        filename = self.filename_pattern.format(
            index=index,
            title=safe_title,
            start=chapter.start_page,
            end=chapter.end_page,
            pages=chapter.page_count
        )
        
        # Ensure .pdf extension
        if not filename.lower().endswith('.pdf'):
            filename += '.pdf'
        
        return self.output_dir / filename
    
    @staticmethod
    def _sanitize_filename(title: str, max_length: int = 100) -> str:
        """
        Sanitize a string to be safe for use as a filename.
        
        Args:
            title: The original title
            max_length: Maximum length for the filename
        
        Returns:
            Sanitized filename-safe string
        """
        # Remove or replace invalid characters
        invalid_chars = r'<>:"/\|?*'
        for char in invalid_chars:
            title = title.replace(char, '_')
        
        # Replace multiple spaces/underscores with single underscore
        title = re.sub(r'[\s_]+', '_', title)
        
        # Remove leading/trailing underscores
        title = title.strip('_')
        
        # Truncate if too long
        if len(title) > max_length:
            title = title[:max_length].rstrip('_')
        
        # Ensure it's not empty
        if not title:
            title = "untitled"
        
        return title


import re
