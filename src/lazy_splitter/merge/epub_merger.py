"""EPUB merger implementation using ebooklib.

Provides :class:`EpubMerger` which can combine multiple EPUB files into a
single e-book with a unified table of contents, de-duplicated shared
resources (images, CSS), and intelligently merged metadata.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

from lazy_splitter.core.base import BaseMerger
from lazy_splitter.core.exceptions import MergeError
from lazy_splitter.core.models import MergeResult
from lazy_splitter.core.utils import ensure_dir, sanitize_filename

try:
    from ebooklib import epub
except ImportError:  # pragma: no cover
    epub = None  # type: ignore[assignment]


class EpubMerger(BaseMerger):
    """Merge multiple EPUB files into a single e-book.

    Requires **ebooklib**.  If the library is not installed a
    :class:`~lazy_splitter.core.exceptions.MergeError` is raised at call
    time.

    Parameters
    ----------
    logger:
        Optional :class:`logging.Logger` instance.
    """

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        super().__init__(logger=logger)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _require_ebooklib() -> None:
        """Raise if ebooklib is not available."""
        if epub is None:
            raise MergeError(
                "ebooklib is required for EPUB merging. "
                "Install it with: pip install ebooklib"
            )

    @staticmethod
    def _content_hash(data: bytes) -> str:
        """Return a short SHA-256 hex digest for *data*."""
        return hashlib.sha256(data).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def merge(
        self,
        paths: Sequence[Path],
        output_path: Path,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        **kwargs: Any,
    ) -> MergeResult:
        """Combine multiple EPUB files into one.

        The merged book contains all chapters from the source files in order.
        Resources (images, stylesheets, fonts) that are byte-identical across
        sources are stored only once.  A unified table of contents is built
        from the original chapter structure of each source.

        Parameters
        ----------
        paths:
            Ordered sequence of EPUB file paths.
        output_path:
            Destination path for the merged EPUB.
        progress_callback:
            Optional callable invoked with ``(current_index, total)`` after
            each source EPUB is processed.
        **kwargs:
            ``title`` -- title for the merged book (default: generated from
            first source).  ``author`` -- author string for the merged book.
            ``language`` -- language code (default: ``"en"``).

        Returns
        -------
        MergeResult

        Raises
        ------
        MergeError
            If ebooklib is missing, any input file is invalid, or writing
            fails.
        """
        self._require_ebooklib()

        validated = self._validate_inputs(paths)
        output_path = Path(output_path)
        ensure_dir(output_path.parent)

        start_time = time.monotonic()
        total = len(validated)

        merged_book = epub.EpubBook()

        # Track resources we have already added (by content hash) to
        # de-duplicate shared images, CSS, and fonts.
        seen_resources: Dict[str, str] = {}  # content_hash -> item file_name
        all_spine_items: List[Any] = ["nav"]
        all_toc: List[Any] = []
        chapter_count = 0

        first_metadata_set = False

        try:
            for idx, epub_path in enumerate(validated):
                self.logger.debug(
                    "Processing %s (%d/%d)", epub_path.name, idx + 1, total,
                )

                src_book = epub.read_epub(str(epub_path), options={"ignore_ncx": True})

                # ---- Metadata (use first book's metadata as base) ----
                if not first_metadata_set:
                    self._apply_metadata(merged_book, src_book, **kwargs)
                    first_metadata_set = True

                # Maps old item file_name -> new item file_name (after
                # potential prefix to avoid collisions).
                name_map: Dict[str, str] = {}
                prefix = f"part{idx + 1}_"

                # ---- Resources (images, CSS, fonts) ----
                for item in src_book.get_items():
                    if item.get_type() in (
                        epub.ITEM_IMAGE,
                        epub.ITEM_STYLE,
                        epub.ITEM_FONT,
                    ):
                        content = item.get_content()
                        content_h = self._content_hash(content)

                        if content_h in seen_resources:
                            # Resource already exists -- record the mapping
                            # so chapter HTML references can be rewritten.
                            name_map[item.get_name()] = seen_resources[content_h]
                        else:
                            new_name = prefix + item.get_name()
                            new_item = epub.EpubItem(
                                uid=prefix + (item.id or item.get_name()),
                                file_name=new_name,
                                media_type=item.media_type,
                                content=content,
                            )
                            merged_book.add_item(new_item)
                            seen_resources[content_h] = new_name
                            name_map[item.get_name()] = new_name

                # ---- Chapters (XHTML documents) ----
                src_toc_section: List[Any] = []
                section_title = epub_path.stem

                for item in src_book.get_items_of_type(epub.ITEM_DOCUMENT):
                    old_name = item.get_name()
                    new_name = prefix + old_name
                    name_map[old_name] = new_name

                    content = item.get_content()
                    # Rewrite internal references to renamed resources
                    content = self._rewrite_references(content, name_map)

                    new_chapter = epub.EpubHtml(
                        uid=prefix + (item.id or old_name),
                        title=item.title or section_title,
                        file_name=new_name,
                        lang=item.lang or "en",
                    )
                    new_chapter.set_content(content)
                    merged_book.add_item(new_chapter)

                    all_spine_items.append(new_chapter)
                    src_toc_section.append(new_chapter)
                    chapter_count += 1

                # Build a TOC section for this source file
                if src_toc_section:
                    section_link = epub.Section(section_title)
                    all_toc.append((section_link, src_toc_section))

                if progress_callback is not None:
                    progress_callback(idx + 1, total)

            # ---- Finalise the merged book ----
            merged_book.toc = all_toc
            merged_book.spine = all_spine_items

            # Required navigation items
            merged_book.add_item(epub.EpubNcx())
            merged_book.add_item(epub.EpubNav())

            epub.write_epub(str(output_path), merged_book)

        except Exception as exc:
            if not isinstance(exc, MergeError):
                raise MergeError(
                    f"Failed to merge EPUBs: {exc}",
                    path=str(output_path),
                ) from exc
            raise

        elapsed = time.monotonic() - start_time
        self.logger.info(
            "Merged %d EPUBs (%d chapters) into %s (%.2fs)",
            total,
            chapter_count,
            output_path.name,
            elapsed,
        )

        return MergeResult(
            output_path=output_path,
            source_paths=list(validated),
            duration_seconds=elapsed,
            metadata={
                "chapter_count": chapter_count,
                "unique_resources": len(seen_resources),
            },
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_metadata(
        merged_book: Any,
        src_book: Any,
        **kwargs: Any,
    ) -> None:
        """Set metadata on *merged_book* from *src_book* and overrides.

        Parameters
        ----------
        merged_book:
            The new ``epub.EpubBook`` being assembled.
        src_book:
            The first source ``epub.EpubBook`` whose metadata serves as a
            baseline.
        **kwargs:
            Optional overrides: ``title``, ``author``, ``language``.
        """
        # Extract title from source or use override
        title = kwargs.get("title")
        if not title:
            src_titles = src_book.get_metadata("DC", "title")
            title = src_titles[0][0] if src_titles else "Merged Book"
        merged_book.set_title(title)

        # Language
        language = kwargs.get("language", "en")
        src_langs = src_book.get_metadata("DC", "language")
        if src_langs and "language" not in kwargs:
            language = src_langs[0][0]
        merged_book.set_language(language)

        # Author
        author = kwargs.get("author")
        if not author:
            src_authors = src_book.get_metadata("DC", "creator")
            author = src_authors[0][0] if src_authors else "lazy-splitter"
        merged_book.add_author(author)

        # Identifier
        merged_book.set_identifier("lazy-splitter-merged-epub")

    @staticmethod
    def _rewrite_references(
        content: bytes,
        name_map: Dict[str, str],
    ) -> bytes:
        """Rewrite resource paths in *content* according to *name_map*.

        This performs simple byte-level replacements for each old resource
        name that has been remapped to a new prefixed name.

        Parameters
        ----------
        content:
            Raw XHTML bytes of a chapter.
        name_map:
            Mapping of ``old_file_name -> new_file_name``.

        Returns
        -------
        bytes
            Updated content with all references rewritten.
        """
        for old_name, new_name in name_map.items():
            if old_name != new_name:
                content = content.replace(
                    old_name.encode("utf-8"),
                    new_name.encode("utf-8"),
                )
        return content
