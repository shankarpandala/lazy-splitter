"""PDF merger implementation using PyMuPDF (fitz).

Provides :class:`PDFMerger` which can combine multiple PDF files into one,
generate a table of contents from filenames, interleave pages from two
documents, and overlay a watermark or letterhead onto every page.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from lazy_splitter.core.base import BaseMerger
from lazy_splitter.core.exceptions import MergeError
from lazy_splitter.core.models import MergeResult
from lazy_splitter.core.utils import ensure_dir, sanitize_filename

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore[assignment]


class PDFMerger(BaseMerger):
    """Merge, interleave, or overlay PDF documents.

    All public methods require **PyMuPDF** (``fitz``).  If the library is not
    installed a :class:`~lazy_splitter.core.exceptions.MergeError` is raised
    at call time.

    Parameters
    ----------
    logger:
        Optional :class:`logging.Logger` instance.  A module-level logger is
        created automatically when omitted.
    """

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        super().__init__(logger=logger)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _require_fitz() -> None:
        """Raise if PyMuPDF is not available."""
        if fitz is None:
            raise MergeError(
                "PyMuPDF (fitz) is required for PDF merging. "
                "Install it with: pip install PyMuPDF"
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def merge(
        self,
        paths: Sequence[Path],
        output_path: Path,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        *,
        generate_toc: bool = False,
        renumber_pages: bool = False,
        add_bookmarks: bool = False,
        **kwargs: Any,
    ) -> MergeResult:
        """Combine multiple PDF files into a single document.

        Parameters
        ----------
        paths:
            Ordered sequence of PDF file paths.
        output_path:
            Destination path for the merged PDF.
        progress_callback:
            Optional callable invoked with ``(current_index, total)`` after
            each source PDF is appended.
        generate_toc:
            If ``True``, create a table-of-contents from the source file
            names (sans extension).
        renumber_pages:
            If ``True``, insert sequential page labels so that page numbers
            restart from 1 in the merged output.
        add_bookmarks:
            If ``True``, add PDF bookmarks at the boundary of each source
            file using its filename as the bookmark title.
        **kwargs:
            Reserved for future options.

        Returns
        -------
        MergeResult
            Describes the output file and source inputs.

        Raises
        ------
        MergeError
            If PyMuPDF is missing, any input file is invalid, or an I/O
            error occurs during writing.
        """
        self._require_fitz()

        validated = self._validate_inputs(paths)
        output_path = Path(output_path)
        ensure_dir(output_path.parent)

        start_time = time.monotonic()
        total = len(validated)

        merged_doc = fitz.open()
        toc_entries: List[List[Any]] = []

        try:
            for idx, pdf_path in enumerate(validated):
                self.logger.debug("Appending %s (%d/%d)", pdf_path.name, idx + 1, total)

                src_doc = fitz.open(str(pdf_path))
                page_offset = merged_doc.page_count

                merged_doc.insert_pdf(src_doc)

                # Build TOC / bookmark entry
                if generate_toc or add_bookmarks:
                    title = pdf_path.stem
                    # Level 1, title, target page (1-indexed)
                    toc_entries.append([1, title, page_offset + 1])

                src_doc.close()

                if progress_callback is not None:
                    progress_callback(idx + 1, total)

            if toc_entries and (generate_toc or add_bookmarks):
                merged_doc.set_toc(toc_entries)

            if renumber_pages:
                self._apply_page_labels(merged_doc, validated)

            merged_doc.save(str(output_path))
        except Exception as exc:
            if not isinstance(exc, MergeError):
                raise MergeError(
                    f"Failed to merge PDFs: {exc}",
                    path=str(output_path),
                ) from exc
            raise
        finally:
            merged_doc.close()

        elapsed = time.monotonic() - start_time
        self.logger.info(
            "Merged %d PDFs into %s (%.2fs)", total, output_path.name, elapsed,
        )

        return MergeResult(
            output_path=output_path,
            source_paths=list(validated),
            duration_seconds=elapsed,
            metadata={
                "page_count": self._count_pages(output_path),
                "generate_toc": generate_toc,
                "add_bookmarks": add_bookmarks,
                "renumber_pages": renumber_pages,
            },
        )

    def merge_with_toc(
        self,
        pdf_paths: Sequence[Path],
        output_path: Path,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> MergeResult:
        """Merge PDFs and auto-generate a TOC from source filenames.

        This is a convenience wrapper around :meth:`merge` with
        ``generate_toc=True`` and ``add_bookmarks=True``.

        Parameters
        ----------
        pdf_paths:
            Ordered sequence of PDF file paths.
        output_path:
            Destination for the merged file.
        progress_callback:
            Optional progress callable.

        Returns
        -------
        MergeResult
        """
        return self.merge(
            pdf_paths,
            output_path,
            progress_callback=progress_callback,
            generate_toc=True,
            add_bookmarks=True,
        )

    def interleave(
        self,
        pdf_path_a: Path,
        pdf_path_b: Path,
        output_path: Path,
    ) -> MergeResult:
        """Interleave pages from two PDFs (A1, B1, A2, B2, ...).

        Useful for combining front/back scans into a single document.  If the
        documents differ in length, remaining pages from the longer document
        are appended at the end.

        Parameters
        ----------
        pdf_path_a:
            First PDF (provides pages at odd positions).
        pdf_path_b:
            Second PDF (provides pages at even positions).
        output_path:
            Destination for the interleaved file.

        Returns
        -------
        MergeResult
        """
        self._require_fitz()

        validated_a = self._validate_inputs([pdf_path_a])[0]
        validated_b = self._validate_inputs([pdf_path_b])[0]
        output_path = Path(output_path)
        ensure_dir(output_path.parent)

        start_time = time.monotonic()

        doc_a = fitz.open(str(validated_a))
        doc_b = fitz.open(str(validated_b))
        merged_doc = fitz.open()

        try:
            max_pages = max(doc_a.page_count, doc_b.page_count)

            for i in range(max_pages):
                if i < doc_a.page_count:
                    merged_doc.insert_pdf(doc_a, from_page=i, to_page=i)
                if i < doc_b.page_count:
                    merged_doc.insert_pdf(doc_b, from_page=i, to_page=i)

            merged_doc.save(str(output_path))
        except Exception as exc:
            if not isinstance(exc, MergeError):
                raise MergeError(
                    f"Failed to interleave PDFs: {exc}",
                    path=str(output_path),
                ) from exc
            raise
        finally:
            doc_a.close()
            doc_b.close()
            merged_doc.close()

        elapsed = time.monotonic() - start_time
        self.logger.info(
            "Interleaved %s + %s into %s (%.2fs)",
            validated_a.name,
            validated_b.name,
            output_path.name,
            elapsed,
        )

        return MergeResult(
            output_path=output_path,
            source_paths=[validated_a, validated_b],
            duration_seconds=elapsed,
            metadata={
                "page_count": self._count_pages(output_path),
                "pages_a": doc_a.page_count,
                "pages_b": doc_b.page_count,
            },
        )

    def overlay(
        self,
        base_path: Path,
        overlay_path: Path,
        output_path: Path,
    ) -> MergeResult:
        """Overlay a watermark or letterhead PDF onto every page of the base PDF.

        The first page of *overlay_path* is rendered on top of every page of
        *base_path*.  This is commonly used for watermarks, letterheads, or
        confidential stamps.

        Parameters
        ----------
        base_path:
            The main PDF document.
        overlay_path:
            A single-page (or multi-page) PDF used as the overlay.  If it
            has multiple pages, each base page uses the corresponding overlay
            page; if the overlay is shorter, its last page is repeated.
        output_path:
            Destination for the output file.

        Returns
        -------
        MergeResult
        """
        self._require_fitz()

        validated_base = self._validate_inputs([base_path])[0]
        validated_overlay = self._validate_inputs([overlay_path])[0]
        output_path = Path(output_path)
        ensure_dir(output_path.parent)

        start_time = time.monotonic()

        base_doc = fitz.open(str(validated_base))
        overlay_doc = fitz.open(str(validated_overlay))

        try:
            overlay_page_count = overlay_doc.page_count

            for page_idx in range(base_doc.page_count):
                base_page = base_doc[page_idx]
                # Pick the matching overlay page, or the last one available
                overlay_idx = min(page_idx, overlay_page_count - 1)
                overlay_page = overlay_doc[overlay_idx]

                # Render overlay page as an XObject and place it on the base page
                overlay_rect = base_page.rect
                base_page.show_pdf_page(overlay_rect, overlay_doc, overlay_idx)

            base_doc.save(str(output_path))
        except Exception as exc:
            if not isinstance(exc, MergeError):
                raise MergeError(
                    f"Failed to overlay PDFs: {exc}",
                    path=str(output_path),
                ) from exc
            raise
        finally:
            base_doc.close()
            overlay_doc.close()

        elapsed = time.monotonic() - start_time
        self.logger.info(
            "Applied overlay %s to %s -> %s (%.2fs)",
            validated_overlay.name,
            validated_base.name,
            output_path.name,
            elapsed,
        )

        return MergeResult(
            output_path=output_path,
            source_paths=[validated_base, validated_overlay],
            duration_seconds=elapsed,
            metadata={
                "page_count": self._count_pages(output_path),
                "overlay_pages": overlay_page_count,
            },
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_page_labels(
        doc: Any,
        source_paths: List[Path],
    ) -> None:
        """Apply sequential page labels to *doc* so each source restarts at 1.

        Parameters
        ----------
        doc:
            An open ``fitz.Document`` that has already had all pages inserted.
        source_paths:
            The original source paths (in order) so page boundaries can be
            calculated.
        """
        # Re-open each source to learn its page count and build label rules.
        offset = 0
        for src in source_paths:
            src_doc = fitz.open(str(src))
            count = src_doc.page_count
            src_doc.close()

            # fitz page labels use set_page_labels (PyMuPDF >= 1.23).  If the
            # API is not available we silently skip -- this is a best-effort
            # convenience feature.
            if hasattr(doc, "set_page_labels"):
                doc.set_page_labels(
                    [{"startpage": offset, "prefix": "", "style": "D", "firstpagenum": 1}]
                )
            offset += count

    @staticmethod
    def _count_pages(pdf_path: Path) -> int:
        """Return the page count of an existing PDF file."""
        try:
            doc = fitz.open(str(pdf_path))
            count = doc.page_count
            doc.close()
            return count
        except Exception:
            return 0
