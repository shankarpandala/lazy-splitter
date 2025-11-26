"""EPUB chapter detection functionality."""

from pathlib import Path
from typing import List, Literal, Tuple
from lxml import html as lxml_html
import ebooklib
from ebooklib import epub

from epub_splitter.models import EpubChapter, EpubDetectionResult


DetectionStrategy = Literal["native", "structural", "manifest", "hybrid"]
SensitivityLevel = Literal["low", "medium", "high"]


class EpubChapterDetector:
    """Detects chapters in EPUB files using various strategies."""

    def __init__(
        self,
        strategy: DetectionStrategy = "hybrid",
        sensitivity: SensitivityLevel = "medium",
        toc_level: int = 1,
    ):
        """
        Initialize the detector.

        Args:
            strategy: Detection strategy to use
            sensitivity: Sensitivity level for structural detection
            toc_level: Which TOC hierarchy level to extract (1=top-level, 2=subsections, etc.)
        """
        self.strategy = strategy
        self.sensitivity = sensitivity
        self.toc_level = toc_level

    def detect(self, epub_path: Path) -> EpubDetectionResult:
        """
        Detect chapters in an EPUB file.

        Args:
            epub_path: Path to the EPUB file

        Returns:
            EpubDetectionResult containing detected chapters
        """
        book = epub.read_epub(str(epub_path))

        # Get content files count
        content_files = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
        total_files = len(content_files)

        # Try detection strategies based on selected strategy
        if self.strategy == "native":
            chapters, has_toc = self._detect_from_toc(book)
            strategy_used = "native"
        elif self.strategy == "structural":
            chapters = self._detect_from_structure(book)
            has_toc = False
            strategy_used = "structural"
        elif self.strategy == "manifest":
            chapters = self._detect_from_manifest(book)
            has_toc = False
            strategy_used = "manifest"
        else:  # hybrid
            chapters, has_toc = self._detect_from_toc(book)
            if not chapters:
                chapters = self._detect_from_structure(book)
                strategy_used = "structural (fallback)"
            else:
                strategy_used = "native"

            if not chapters:
                chapters = self._detect_from_manifest(book)
                strategy_used = "manifest (fallback)"

        return EpubDetectionResult(
            chapters=chapters,
            strategy_used=strategy_used,
            total_files=total_files,
            has_toc=has_toc,
        )

    def _detect_from_toc(self, book: epub.EpubBook) -> Tuple[List[EpubChapter], bool]:
        """
        Detect chapters from EPUB table of contents.

        Args:
            book: EpubBook object

        Returns:
            Tuple of (list of chapters, whether TOC exists)
        """
        chapters: List[EpubChapter] = []

        try:
            toc = book.toc
            if not toc:
                return [], False

            # Flatten TOC and filter by level
            self._extract_toc_entries(toc, chapters, current_level=1)

            # Filter by requested level
            if self.toc_level > 0:
                chapters = [ch for ch in chapters if ch.level == self.toc_level]

            return chapters, True

        except (AttributeError, Exception):
            return [], False

    def _extract_toc_entries(
        self,
        toc_items: List,
        chapters: List[EpubChapter],
        current_level: int = 1,
    ) -> None:
        """
        Recursively extract TOC entries.

        Args:
            toc_items: TOC items (can be nested)
            chapters: List to append chapters to
            current_level: Current hierarchy level
        """
        for item in toc_items:
            if isinstance(item, tuple):
                # Nested section: (Section, [children])
                section, children = item
                if hasattr(section, "title") and hasattr(section, "href"):
                    # Parse href to get file path and anchor
                    file_path, html_id = self._parse_href(section.href)

                    chapters.append(
                        EpubChapter(
                            title=section.title,
                            file_path=file_path,
                            html_id=html_id,
                            level=current_level,
                            detection_method="native",
                            confidence=1.0,
                        )
                    )

                # Process children
                if children:
                    self._extract_toc_entries(children, chapters, current_level + 1)

            elif hasattr(item, "title") and hasattr(item, "href"):
                # Simple link item
                file_path, html_id = self._parse_href(item.href)

                chapters.append(
                    EpubChapter(
                        title=item.title,
                        file_path=file_path,
                        html_id=html_id,
                        level=current_level,
                        detection_method="native",
                        confidence=1.0,
                    )
                )

    def _parse_href(self, href: str) -> Tuple[str, str]:
        """
        Parse href into file path and HTML ID.

        Args:
            href: HREF string (e.g., "chapter1.xhtml#section2")

        Returns:
            Tuple of (file_path, html_id)
        """
        if "#" in href:
            file_path, html_id = href.split("#", 1)
            return file_path, html_id
        return href, None

    def _detect_from_structure(self, book: epub.EpubBook) -> List[EpubChapter]:
        """
        Detect chapters by analyzing HTML structure (headings).

        Args:
            book: EpubBook object

        Returns:
            List of detected chapters
        """
        chapters: List[EpubChapter] = []

        # Heading tags to look for based on sensitivity
        heading_tags = {
            "low": ["h1"],
            "medium": ["h1", "h2"],
            "high": ["h1", "h2", "h3"],
        }
        tags = heading_tags.get(self.sensitivity, ["h1", "h2"])

        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            try:
                content = item.get_content()
                tree = lxml_html.fromstring(content)

                # Find headings
                for tag in tags:
                    headings = tree.xpath(f"//{tag}")

                    for heading in headings:
                        title = heading.text_content().strip()
                        if title:
                            # Get heading level (h1=1, h2=2, h3=3)
                            level = int(tag[1])

                            # Calculate confidence based on tag level
                            confidence = 1.0 if tag == "h1" else 0.7 if tag == "h2" else 0.5

                            # Get ID attribute if exists
                            html_id = heading.get("id")

                            chapters.append(
                                EpubChapter(
                                    title=title,
                                    file_path=item.get_name(),
                                    html_id=html_id,
                                    level=level,
                                    detection_method="structural",
                                    confidence=confidence,
                                )
                            )
            except Exception:
                # Skip files that can't be parsed
                continue

        return chapters

    def _detect_from_manifest(self, book: epub.EpubBook) -> List[EpubChapter]:
        """
        Detect chapters from EPUB spine/manifest (one chapter per file).

        Args:
            book: EpubBook object

        Returns:
            List of detected chapters
        """
        chapters: List[EpubChapter] = []

        # Get items in reading order from spine
        for item_id, _ in book.spine:
            item = book.get_item_with_id(item_id)

            if item and item.get_type() == ebooklib.ITEM_DOCUMENT:
                # Try to extract title from first heading or use filename
                title = self._extract_title_from_content(item)
                if not title:
                    title = Path(item.get_name()).stem.replace("_", " ").title()

                chapters.append(
                    EpubChapter(
                        title=title,
                        file_path=item.get_name(),
                        html_id=None,
                        level=1,
                        detection_method="manifest",
                        confidence=0.6,
                    )
                )

        return chapters

    def _extract_title_from_content(self, item: epub.EpubItem) -> str:
        """
        Extract title from HTML content.

        Args:
            item: EPUB item

        Returns:
            Extracted title or empty string
        """
        try:
            content = item.get_content()
            tree = lxml_html.fromstring(content)

            # Try title tag first
            title_elem = tree.find(".//title")
            if title_elem is not None and title_elem.text:
                return title_elem.text.strip()

            # Try first h1
            h1 = tree.find(".//h1")
            if h1 is not None:
                return h1.text_content().strip()

            # Try first h2
            h2 = tree.find(".//h2")
            if h2 is not None:
                return h2.text_content().strip()

        except Exception:
            pass

        return ""
