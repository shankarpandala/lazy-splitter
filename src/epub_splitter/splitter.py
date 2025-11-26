"""EPUB splitting functionality."""

import re
from pathlib import Path
from typing import List, Set
from lxml import html as lxml_html
from ebooklib import epub

from epub_splitter.models import EpubChapter


class EpubSplitter:
    """Handles splitting EPUB files by chapters."""

    def __init__(self, output_dir: Path, filename_pattern: str = "{index:02d}_{title}.epub"):
        """
        Initialize the splitter.

        Args:
            output_dir: Directory where split EPUBs will be saved
            filename_pattern: Pattern for output filenames. Available placeholders:
                - {index}: Chapter index (starts at 1)
                - {title}: Chapter title (sanitized)
                - {file}: Original XHTML filename (without extension)
        """
        self.output_dir = Path(output_dir)
        self.filename_pattern = filename_pattern
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

                return lxml_html.tostring(new_tree, encoding="utf-8")

            # If ID not found, return original content
            return content

        except Exception:
            # If extraction fails, return original content
            return item.get_content()

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

        # Ensure .epub extension
        if not filename.lower().endswith(".epub"):
            filename += ".epub"

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
