"""EPUB splitting functionality."""

import re
from pathlib import Path
from typing import List, Set, Literal
from lxml import html as lxml_html  # type: ignore
from ebooklib import epub  # type: ignore
import fitz  # PyMuPDF

from epub_splitter.models import EpubChapter


OutputFormat = Literal["epub", "pdf"]


class EpubSplitter:
    """Handles splitting EPUB files by chapters."""

    def __init__(
        self,
        output_dir: Path,
        filename_pattern: str = "{index:02d}_{title}.epub",
        output_format: OutputFormat = "epub",
    ):
        """
        Initialize the splitter.

        Args:
            output_dir: Directory where split files will be saved
            filename_pattern: Pattern for output filenames. Available placeholders:
                - {index}: Chapter index (starts at 1)
                - {title}: Chapter title (sanitized)
                - {file}: Original XHTML filename (without extension)
            output_format: Output format - 'epub' or 'pdf'
        """
        self.output_dir = Path(output_dir)
        self.filename_pattern = filename_pattern
        self.output_format = output_format
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def split(
        self,
        epub_path: Path,
        chapters: List[EpubChapter],
        preserve_metadata: bool = True,
    ) -> List[Path]:
        """
        Split an EPUB file into separate files by chapters.

        Args:
            epub_path: Path to the source EPUB file
            chapters: List of chapters to split by
            preserve_metadata: Whether to preserve metadata in split files

        Returns:
            List of paths to the created files (EPUB or PDF)
        """
        if self.output_format == "pdf":
            return self._split_to_pdf(epub_path, chapters, preserve_metadata)
        else:
            return self._split_to_epub(epub_path, chapters, preserve_metadata)

    def _split_to_epub(
        self,
        epub_path: Path,
        chapters: List[EpubChapter],
        preserve_metadata: bool = True,
    ) -> List[Path]:
        """
        Split an EPUB file into separate EPUB files by chapters.

        Args:
            epub_path: Path to the source EPUB file
            chapters: List of chapters to split by
            preserve_metadata: Whether to preserve EPUB metadata in split files

        Returns:
            List of paths to the created EPUB files
        """
        book = epub.read_epub(str(epub_path))
        created_files: List[Path] = []

        for index, chapter in enumerate(chapters, start=1):
            output_path = self._generate_filename(chapter, index)

            # Create new EPUB with chapter content
            new_book = self._create_chapter_epub(book, chapter, preserve_metadata)

            # Write the new EPUB
            epub.write_epub(str(output_path), new_book)
            created_files.append(output_path)

        return created_files

    def _split_to_pdf(
        self,
        epub_path: Path,
        chapters: List[EpubChapter],
        preserve_metadata: bool = True,
    ) -> List[Path]:
        """
        Split an EPUB file into separate PDF files by chapters.

        Args:
            epub_path: Path to the source EPUB file
            chapters: List of chapters to split by
            preserve_metadata: Whether to preserve metadata in PDF files

        Returns:
            List of paths to the created PDF files
        """
        book = epub.read_epub(str(epub_path))
        created_files: List[Path] = []

        for index, chapter in enumerate(chapters, start=1):
            output_path = self._generate_filename(chapter, index)

            # Get chapter content
            main_item = book.get_item_with_href(chapter.file_path)
            if not main_item:
                continue

            # Extract HTML content
            if chapter.html_id:
                html_content = self._extract_chapter_section(main_item, chapter.html_id)
            else:
                html_content = main_item.get_content()

            # Convert HTML to PDF
            pdf_doc = self._html_to_pdf(html_content, chapter.title, preserve_metadata)

            # Save PDF
            pdf_doc.save(str(output_path))
            pdf_doc.close()
            created_files.append(output_path)

        return created_files

    def _html_to_pdf(
        self, html_content: bytes, title: str, preserve_metadata: bool
    ) -> fitz.Document:
        """
        Convert HTML content to PDF.

        Args:
            html_content: HTML content as bytes
            title: Chapter title for metadata
            preserve_metadata: Whether to set metadata

        Returns:
            PyMuPDF Document object
        """
        # Create a new PDF document
        pdf_doc = fitz.open()

        # Extract text from HTML
        try:
            text = lxml_html.fromstring(html_content).text_content()
        except Exception:
            # Fallback to raw HTML decode
            try:
                html_str = html_content.decode("utf-8")
            except UnicodeDecodeError:
                html_str = html_content.decode("latin-1", errors="ignore")
            import re

            text = re.sub(r"<[^>]+>", "", html_str)

        # Create pages and add text
        page_width = 595  # A4 width in points
        page_height = 842  # A4 height in points
        margin = 50
        line_height = 15
        max_chars_per_line = 80

        # Split text into paragraphs
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

        # Create first page
        page = pdf_doc.new_page(width=page_width, height=page_height)
        y_position = margin

        for para in paragraphs:
            # Split paragraph into lines that fit
            words = para.split()
            current_line = ""

            for word in words:
                test_line = current_line + " " + word if current_line else word
                if len(test_line) > max_chars_per_line:
                    # Insert current line and start new one
                    if y_position > page_height - margin:
                        # Need new page
                        page = pdf_doc.new_page(width=page_width, height=page_height)
                        y_position = margin

                    page.insert_text(
                        (margin, y_position),
                        current_line,
                        fontsize=11,
                        fontname="helv",
                    )
                    y_position += line_height
                    current_line = word
                else:
                    current_line = test_line

            # Insert remaining text in line
            if current_line:
                if y_position > page_height - margin:
                    page = pdf_doc.new_page(width=page_width, height=page_height)
                    y_position = margin

                page.insert_text(
                    (margin, y_position),
                    current_line,
                    fontsize=11,
                    fontname="helv",
                )
                y_position += line_height

            # Add paragraph spacing
            y_position += int(line_height / 2)

        # Set metadata
        if preserve_metadata:
            pdf_doc.set_metadata({"title": title, "creator": "lazy-splitter"})

        return pdf_doc

    def _create_chapter_epub(
        self,
        source_book: epub.EpubBook,
        chapter: EpubChapter,
        preserve_metadata: bool,
    ) -> epub.EpubBook:
        """
        Create a new EPUB book for a single chapter.

        Args:
            source_book: Source EPUB book
            chapter: Chapter to extract
            preserve_metadata: Whether to preserve metadata

        Returns:
            New EpubBook instance
        """
        new_book = epub.EpubBook()

        # Set metadata
        if preserve_metadata:
            # Copy basic metadata
            metadata = source_book.metadata
            if metadata:
                for namespace, data in metadata.items():
                    for key, values in data.items():
                        for value in values:
                            if isinstance(value, tuple):
                                new_book.add_metadata(
                                    namespace, key, value[0], value[1] if len(value) > 1 else {}
                                )
                            else:
                                new_book.add_metadata(namespace, key, value)

        # Override title with chapter title
        new_book.set_title(chapter.title)

        # Get the main content item
        main_item = source_book.get_item_with_href(chapter.file_path)

        if main_item:
            # If chapter has HTML ID, extract only that section
            if chapter.html_id:
                content = self._extract_chapter_section(main_item, chapter.html_id)
                new_item = epub.EpubHtml(
                    title=chapter.title,
                    file_name=chapter.file_path,
                    content=content,
                )
            else:
                # Copy entire file
                new_item = epub.EpubHtml(
                    title=chapter.title,
                    file_name=main_item.get_name(),
                    content=main_item.get_content(),
                )

            new_book.add_item(new_item)

            # Copy referenced resources (images, CSS, fonts)
            resources = self._find_referenced_resources(source_book, new_item)
            for resource in resources:
                new_book.add_item(resource)

            # Set spine (reading order)
            new_book.spine = ["nav", new_item]

            # Add navigation
            new_book.toc = (epub.Link(chapter.file_path, chapter.title, "chapter"),)
            new_book.add_item(epub.EpubNcx())
            new_book.add_item(epub.EpubNav())

        return new_book

    def _extract_chapter_section(self, item: epub.EpubItem, html_id: str) -> bytes:
        """
        Extract a specific section from an HTML file by ID.

        Args:
            item: EPUB item containing HTML
            html_id: HTML element ID to extract

        Returns:
            Modified HTML content as bytes
        """
        try:
            content = item.get_content()
            tree = lxml_html.fromstring(content)

            # Find element with the specified ID
            element = tree.get_element_by_id(html_id)

            if element is not None:
                # Create a new HTML document with just this section
                new_tree = lxml_html.fromstring("<html><head></head><body></body></html>")
                body = new_tree.find(".//body")
                body.append(element)

                return lxml_html.tostring(new_tree, encoding="utf-8")  # type: ignore[no-any-return]

            # If ID not found, return original content
            return content  # type: ignore[no-any-return]

        except Exception:
            # If extraction fails, return original content
            return item.get_content()  # type: ignore[no-any-return]

    def _find_referenced_resources(
        self,
        source_book: epub.EpubBook,
        html_item: epub.EpubHtml,
    ) -> Set[epub.EpubItem]:
        """
        Find all resources (images, CSS, fonts) referenced in HTML content.

        Args:
            source_book: Source EPUB book
            html_item: HTML item to scan for references

        Returns:
            Set of referenced EPUB items
        """
        resources: Set[epub.EpubItem] = set()

        try:
            content = html_item.get_content()
            tree = lxml_html.fromstring(content)

            # Find CSS files (link rel="stylesheet")
            for link in tree.xpath('//link[@rel="stylesheet"]'):
                href = link.get("href")
                if href:
                    resource = self._resolve_resource(source_book, html_item, href)
                    if resource:
                        resources.add(resource)

            # Find images
            for img in tree.xpath("//img"):
                src = img.get("src")
                if src:
                    resource = self._resolve_resource(source_book, html_item, src)
                    if resource:
                        resources.add(resource)

            # Find fonts in CSS (basic detection)
            for style in tree.xpath("//style"):
                style_content = style.text_content()
                # Look for url() references in CSS
                urls = re.findall(r'url\(["\']?([^"\')]+)["\']?\)', style_content)
                for url in urls:
                    resource = self._resolve_resource(source_book, html_item, url)
                    if resource:
                        resources.add(resource)

        except Exception:
            pass

        return resources

    def _resolve_resource(
        self,
        source_book: epub.EpubBook,
        base_item: epub.EpubItem,
        href: str,
    ) -> epub.EpubItem:
        """
        Resolve a relative resource reference.

        Args:
            source_book: Source EPUB book
            base_item: Base item for relative path resolution
            href: Resource href (may be relative)

        Returns:
            EPUB item or None if not found
        """
        # Remove fragment identifier
        href = href.split("#")[0]

        # Try direct lookup first
        resource = source_book.get_item_with_href(href)
        if resource:
            return resource

        # Try resolving relative to base item path
        base_path = Path(base_item.get_name()).parent
        resolved_path = (base_path / href).as_posix()

        resource = source_book.get_item_with_href(resolved_path)
        return resource

    def _generate_filename(self, chapter: EpubChapter, index: int) -> Path:
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

        # Get filename without extension
        file_stem = Path(chapter.file_path).stem

        # Format filename using pattern
        filename = self.filename_pattern.format(
            index=index,
            title=safe_title,
            file=file_stem,
        )

        # Ensure correct extension based on output format
        extension = ".pdf" if self.output_format == "pdf" else ".epub"
        if not filename.lower().endswith(extension):
            # Remove any existing extension
            if filename.lower().endswith(".epub") or filename.lower().endswith(".pdf"):
                filename = filename[:-5]
            filename += extension

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
            title = title.replace(char, "_")

        # Replace multiple spaces/underscores with single underscore
        title = re.sub(r"[\s_]+", "_", title)

        # Remove leading/trailing underscores
        title = title.strip("_")

        # Truncate if too long
        if len(title) > max_length:
            title = title[:max_length].rstrip("_")

        # Ensure it's not empty
        if not title:
            title = "untitled"

        return title
