"""Document format converters (PDF, EPUB, Markdown, HTML).

Provides :class:`DocumentConverter` with methods for converting between
document formats.  Heavy external libraries (PyMuPDF, ebooklib, markdown)
are imported lazily so the module can always be loaded even when optional
dependencies are not installed.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lazy_splitter.core.base import BaseConverter
from lazy_splitter.core.exceptions import ConversionError
from lazy_splitter.core.models import ConversionResult
from lazy_splitter.core.utils import ensure_dir, sanitize_filename

# ---------------------------------------------------------------------------
# Optional dependency imports
# ---------------------------------------------------------------------------

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore[assignment]

try:
    import ebooklib  # type: ignore[import-untyped]
    from ebooklib import epub as _epub  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    ebooklib = None  # type: ignore[assignment]
    _epub = None  # type: ignore[assignment]

try:
    import markdown as _markdown  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    _markdown = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def _require_fitz() -> None:
    """Raise :class:`ConversionError` if PyMuPDF is not installed."""
    if fitz is None:
        raise ConversionError(
            "PyMuPDF (fitz) is required for this conversion. "
            "Install it with: pip install PyMuPDF"
        )


def _require_ebooklib() -> None:
    """Raise :class:`ConversionError` if ebooklib is not installed."""
    if ebooklib is None or _epub is None:
        raise ConversionError(
            "ebooklib is required for EPUB conversions. "
            "Install it with: pip install ebooklib"
        )


def _require_markdown() -> None:
    """Raise :class:`ConversionError` if the markdown library is not installed."""
    if _markdown is None:
        raise ConversionError(
            "markdown is required for Markdown conversions. "
            "Install it with: pip install markdown"
        )


class DocumentConverter(BaseConverter):
    """Converter for document formats (PDF, EPUB, Markdown, HTML).

    Each public method handles a specific conversion direction and returns
    the path(s) to the created file(s).  The class also satisfies the
    :class:`~lazy_splitter.core.base.BaseConverter` interface via the
    generic :meth:`convert` entry-point.
    """

    # ------------------------------------------------------------------
    # Supported conversion pairs
    # ------------------------------------------------------------------

    #: All (input_format, output_format) pairs this converter handles.
    _SUPPORTED: List[Tuple[str, str]] = [
        ("pdf", "png"),
        ("pdf", "jpeg"),
        ("pdf", "jpg"),
        ("pdf", "tiff"),
        ("pdf", "bmp"),
        ("pdf", "txt"),
        ("pdf", "text"),
        ("epub", "html"),
        ("epub", "txt"),
        ("epub", "text"),
        ("epub", "md"),
        ("epub", "markdown"),
        ("md", "html"),
        ("markdown", "html"),
        ("html", "pdf"),
        ("htm", "pdf"),
    ]

    @property
    def supported_conversions(self) -> List[Tuple[str, str]]:
        """Return the list of (input_format, output_format) pairs supported."""
        return list(self._SUPPORTED)

    # ------------------------------------------------------------------
    # BaseConverter interface
    # ------------------------------------------------------------------

    def convert(
        self,
        input_path: Path,
        output_path: Path,
        output_format: str,
        **kwargs: Any,
    ) -> Path:
        """Dispatch to the appropriate document conversion method.

        Parameters
        ----------
        input_path:
            Source file path.
        output_path:
            Destination file or directory path.
        output_format:
            Target format identifier (e.g. ``"png"``, ``"txt"``, ``"html"``).
        **kwargs:
            Conversion-specific options forwarded to the underlying method.

        Returns
        -------
        Path
            Path to the created output file.

        Raises
        ------
        ConversionError
            If the conversion direction is unsupported or an error occurs.
        """
        input_path = Path(input_path)
        output_path = Path(output_path)
        self._validate_input(input_path)

        in_ext = input_path.suffix.lower().lstrip(".")
        out_ext = output_format.lower().lstrip(".")

        result_path: Any  # may be Path or List[Path]

        if in_ext == "pdf" and out_ext in ("png", "jpeg", "jpg", "tiff", "bmp"):
            dpi = kwargs.get("dpi", 150)
            result_path = self.pdf_to_images(
                input_path, output_path.parent, image_format=out_ext, dpi=dpi
            )
        elif in_ext == "pdf" and out_ext in ("txt", "text"):
            result_path = self.pdf_to_text(input_path, output_path)
        elif in_ext == "epub" and out_ext == "html":
            result_path = self.epub_to_html(input_path, output_path.parent)
        elif in_ext == "epub" and out_ext in ("txt", "text"):
            result_path = self.epub_to_text(input_path, output_path)
        elif in_ext == "epub" and out_ext in ("md", "markdown"):
            result_path = self.epub_to_markdown(input_path, output_path)
        elif in_ext in ("md", "markdown") and out_ext == "html":
            result_path = self.markdown_to_html(input_path, output_path)
        elif in_ext in ("html", "htm") and out_ext == "pdf":
            result_path = self.html_to_pdf(input_path, output_path)
        else:
            raise ConversionError(
                f"Unsupported document conversion: {in_ext} -> {out_ext}",
                input_format=in_ext,
                output_format=out_ext,
            )

        # Normalise result_path to a single Path
        if isinstance(result_path, list):
            return result_path[0] if result_path else output_path
        return result_path

    # ------------------------------------------------------------------
    # PDF conversions
    # ------------------------------------------------------------------

    def pdf_to_images(
        self,
        pdf_path: Path,
        output_dir: Path,
        image_format: str = "png",
        dpi: int = 150,
    ) -> List[Path]:
        """Extract each page of a PDF as a raster image.

        Parameters
        ----------
        pdf_path:
            Path to the source PDF file.
        output_dir:
            Directory where images will be written.
        image_format:
            Target image format (``"png"``, ``"jpeg"``, etc.).
        dpi:
            Resolution in dots-per-inch for rasterisation.

        Returns
        -------
        list of Path
            Paths to the created image files, one per page.

        Raises
        ------
        ConversionError
            If PyMuPDF is not installed or the PDF cannot be read.
        """
        _require_fitz()
        pdf_path = Path(pdf_path)
        output_dir = ensure_dir(output_dir)

        # Normalise the format string for PyMuPDF's Pixmap.save()
        fmt = image_format.lower().replace("jpg", "jpeg")
        ext = "jpg" if fmt == "jpeg" else fmt

        created: List[Path] = []
        try:
            doc = fitz.open(str(pdf_path))  # type: ignore[union-attr]
        except Exception as exc:
            raise ConversionError(
                f"Failed to open PDF: {exc}", path=str(pdf_path)
            ) from exc

        try:
            zoom = dpi / 72.0
            matrix = fitz.Matrix(zoom, zoom)  # type: ignore[union-attr]
            for page_num in range(len(doc)):
                page = doc[page_num]
                pix = page.get_pixmap(matrix=matrix)
                filename = f"page_{page_num + 1:04d}.{ext}"
                out_path = output_dir / filename
                pix.save(str(out_path))
                created.append(out_path)
                self.logger.debug(
                    "Rendered page %d/%d -> %s", page_num + 1, len(doc), out_path
                )
        finally:
            doc.close()

        self.logger.info(
            "Extracted %d pages from %s as %s images at %d DPI",
            len(created),
            pdf_path.name,
            fmt.upper(),
            dpi,
        )
        return created

    def pdf_to_text(
        self,
        pdf_path: Path,
        output_path: Path,
    ) -> Path:
        """Extract all text content from a PDF file.

        Parameters
        ----------
        pdf_path:
            Path to the source PDF file.
        output_path:
            Path for the output text file.

        Returns
        -------
        Path
            The path to the created text file.

        Raises
        ------
        ConversionError
            If PyMuPDF is not installed or the PDF cannot be read.
        """
        _require_fitz()
        pdf_path = Path(pdf_path)
        output_path = Path(output_path)
        ensure_dir(output_path.parent)

        try:
            doc = fitz.open(str(pdf_path))  # type: ignore[union-attr]
        except Exception as exc:
            raise ConversionError(
                f"Failed to open PDF: {exc}", path=str(pdf_path)
            ) from exc

        text_parts: List[str] = []
        try:
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text("text")
                if text.strip():
                    text_parts.append(text)
        finally:
            doc.close()

        full_text = "\n\n".join(text_parts)
        output_path.write_text(full_text, encoding="utf-8")
        self.logger.info(
            "Extracted text from %s (%d characters) -> %s",
            pdf_path.name,
            len(full_text),
            output_path,
        )
        return output_path

    @staticmethod
    def images_to_pdf(
        image_paths: List[Path],
        output_path: Path,
    ) -> Path:
        """Combine a sequence of images into a single PDF.

        Parameters
        ----------
        image_paths:
            Ordered list of image file paths.
        output_path:
            Destination path for the combined PDF.

        Returns
        -------
        Path
            The path to the created PDF file.

        Raises
        ------
        ConversionError
            If PyMuPDF is not installed, the image list is empty, or any
            image cannot be read.
        """
        _require_fitz()
        if not image_paths:
            raise ConversionError("No images provided for PDF assembly")

        output_path = Path(output_path)
        ensure_dir(output_path.parent)

        doc = fitz.open()  # type: ignore[union-attr]
        try:
            for img_path in image_paths:
                img_path = Path(img_path)
                if not img_path.is_file():
                    raise ConversionError(
                        f"Image file not found: {img_path}", path=str(img_path)
                    )
                img_doc = fitz.open(str(img_path))  # type: ignore[union-attr]
                try:
                    rect = img_doc[0].rect
                    pdf_bytes = img_doc.convert_to_pdf()
                finally:
                    img_doc.close()

                img_pdf = fitz.open("pdf", pdf_bytes)  # type: ignore[union-attr]
                try:
                    doc.insert_pdf(img_pdf)
                finally:
                    img_pdf.close()

            doc.save(str(output_path))
        finally:
            doc.close()

        logger.info(
            "Combined %d images into PDF -> %s", len(image_paths), output_path
        )
        return output_path

    # ------------------------------------------------------------------
    # EPUB conversions
    # ------------------------------------------------------------------

    def epub_to_html(
        self,
        epub_path: Path,
        output_dir: Path,
    ) -> List[Path]:
        """Export each chapter of an EPUB as a separate HTML file.

        Parameters
        ----------
        epub_path:
            Path to the source EPUB file.
        output_dir:
            Directory where HTML files will be written.

        Returns
        -------
        list of Path
            Paths to the created HTML files.

        Raises
        ------
        ConversionError
            If ebooklib is not installed or the EPUB cannot be read.
        """
        _require_ebooklib()
        epub_path = Path(epub_path)
        output_dir = ensure_dir(output_dir)

        try:
            book = _epub.read_epub(str(epub_path))  # type: ignore[union-attr]
        except Exception as exc:
            raise ConversionError(
                f"Failed to read EPUB: {exc}", path=str(epub_path)
            ) from exc

        created: List[Path] = []
        items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))  # type: ignore[union-attr]

        for idx, item in enumerate(items):
            title = item.get_name()
            safe_name = sanitize_filename(
                Path(title).stem if title else f"chapter_{idx + 1:03d}"
            )
            out_file = output_dir / f"{safe_name}.html"

            content = item.get_content()
            if isinstance(content, bytes):
                content = content.decode("utf-8", errors="replace")

            out_file.write_text(content, encoding="utf-8")
            created.append(out_file)
            self.logger.debug("Exported EPUB item %s -> %s", title, out_file)

        self.logger.info(
            "Exported %d HTML files from %s", len(created), epub_path.name
        )
        return created

    def epub_to_text(
        self,
        epub_path: Path,
        output_path: Path,
    ) -> Path:
        """Export an EPUB as plain text.

        HTML tags are stripped to produce a text-only representation of the
        book content.

        Parameters
        ----------
        epub_path:
            Path to the source EPUB file.
        output_path:
            Path for the output text file.

        Returns
        -------
        Path
            The path to the created text file.

        Raises
        ------
        ConversionError
            If ebooklib is not installed or the EPUB cannot be read.
        """
        _require_ebooklib()
        epub_path = Path(epub_path)
        output_path = Path(output_path)
        ensure_dir(output_path.parent)

        try:
            book = _epub.read_epub(str(epub_path))  # type: ignore[union-attr]
        except Exception as exc:
            raise ConversionError(
                f"Failed to read EPUB: {exc}", path=str(epub_path)
            ) from exc

        text_parts: List[str] = []
        items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))  # type: ignore[union-attr]

        for item in items:
            content = item.get_content()
            if isinstance(content, bytes):
                content = content.decode("utf-8", errors="replace")
            # Strip HTML tags
            clean = _strip_html(content)
            if clean.strip():
                text_parts.append(clean.strip())

        full_text = "\n\n".join(text_parts)
        output_path.write_text(full_text, encoding="utf-8")
        self.logger.info(
            "Exported text from %s (%d characters) -> %s",
            epub_path.name,
            len(full_text),
            output_path,
        )
        return output_path

    def epub_to_markdown(
        self,
        epub_path: Path,
        output_path: Path,
    ) -> Path:
        """Convert an EPUB to Markdown format.

        Performs a best-effort HTML-to-Markdown conversion of each content
        document in the EPUB, preserving headings, paragraphs, and basic
        inline formatting.

        Parameters
        ----------
        epub_path:
            Path to the source EPUB file.
        output_path:
            Path for the output Markdown file.

        Returns
        -------
        Path
            The path to the created Markdown file.

        Raises
        ------
        ConversionError
            If ebooklib is not installed or the EPUB cannot be read.
        """
        _require_ebooklib()
        epub_path = Path(epub_path)
        output_path = Path(output_path)
        ensure_dir(output_path.parent)

        try:
            book = _epub.read_epub(str(epub_path))  # type: ignore[union-attr]
        except Exception as exc:
            raise ConversionError(
                f"Failed to read EPUB: {exc}", path=str(epub_path)
            ) from exc

        md_parts: List[str] = []
        items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))  # type: ignore[union-attr]

        for item in items:
            content = item.get_content()
            if isinstance(content, bytes):
                content = content.decode("utf-8", errors="replace")
            md_text = _html_to_markdown(content)
            if md_text.strip():
                md_parts.append(md_text.strip())

        full_md = "\n\n---\n\n".join(md_parts)
        output_path.write_text(full_md, encoding="utf-8")
        self.logger.info(
            "Converted EPUB to Markdown (%d characters) -> %s",
            len(full_md),
            output_path,
        )
        return output_path

    # ------------------------------------------------------------------
    # Markdown / HTML conversions
    # ------------------------------------------------------------------

    def markdown_to_html(
        self,
        md_path: Path,
        output_path: Path,
    ) -> Path:
        """Convert a Markdown file to HTML.

        Parameters
        ----------
        md_path:
            Path to the source Markdown file.
        output_path:
            Path for the output HTML file.

        Returns
        -------
        Path
            The path to the created HTML file.

        Raises
        ------
        ConversionError
            If the markdown library is not installed or the file cannot be read.
        """
        _require_markdown()
        md_path = Path(md_path)
        output_path = Path(output_path)
        ensure_dir(output_path.parent)

        try:
            md_text = md_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConversionError(
                f"Failed to read Markdown file: {exc}", path=str(md_path)
            ) from exc

        html_body = _markdown.convert(md_text)  # type: ignore[union-attr]

        html_doc = (
            "<!DOCTYPE html>\n"
            "<html>\n"
            "<head><meta charset=\"utf-8\"><title>"
            + _escape_html(md_path.stem)
            + "</title></head>\n"
            "<body>\n"
            + html_body
            + "\n</body>\n"
            "</html>\n"
        )

        output_path.write_text(html_doc, encoding="utf-8")
        self.logger.info("Converted Markdown -> HTML: %s", output_path)
        return output_path

    def html_to_pdf(
        self,
        html_path: Path,
        output_path: Path,
    ) -> Path:
        """Convert an HTML file to PDF (best-effort via PyMuPDF Story API).

        This uses PyMuPDF's ``Story`` class for HTML rendering when available,
        falling back to a simple text-based conversion for older PyMuPDF
        versions.

        Parameters
        ----------
        html_path:
            Path to the source HTML file.
        output_path:
            Path for the output PDF file.

        Returns
        -------
        Path
            The path to the created PDF file.

        Raises
        ------
        ConversionError
            If PyMuPDF is not installed or the HTML cannot be processed.
        """
        _require_fitz()
        html_path = Path(html_path)
        output_path = Path(output_path)
        ensure_dir(output_path.parent)

        try:
            html_content = html_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConversionError(
                f"Failed to read HTML file: {exc}", path=str(html_path)
            ) from exc

        try:
            # Try the Story API (PyMuPDF >= 1.21)
            if hasattr(fitz, "Story"):
                story = fitz.Story(html=html_content)  # type: ignore[union-attr]
                writer = fitz.DocumentWriter(str(output_path))  # type: ignore[union-attr]
                mediabox = fitz.paper_rect("a4")  # type: ignore[union-attr]
                while True:
                    device = writer.begin_page(mediabox)
                    more, _ = story.place(mediabox)
                    story.draw(device)
                    writer.end_page()
                    if not more:
                        break
                writer.close()
            else:
                # Fallback: insert the HTML text content as plain text on pages
                self.logger.warning(
                    "PyMuPDF Story API not available; using text-only fallback"
                )
                plain = _strip_html(html_content)
                doc = fitz.open()  # type: ignore[union-attr]
                try:
                    page = doc.new_page(width=595, height=842)  # A4
                    text_rect = fitz.Rect(50, 50, 545, 792)  # type: ignore[union-attr]
                    page.insert_textbox(
                        text_rect,
                        plain,
                        fontsize=11,
                        fontname="helv",
                    )
                    doc.save(str(output_path))
                finally:
                    doc.close()
        except ConversionError:
            raise
        except Exception as exc:
            raise ConversionError(
                f"HTML to PDF conversion failed: {exc}", path=str(html_path)
            ) from exc

        self.logger.info("Converted HTML -> PDF: %s", output_path)
        return output_path


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

# Simple regex for stripping HTML tags.
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\n{3,}")


def _strip_html(html: str) -> str:
    """Remove HTML tags and collapse excessive whitespace."""
    # Replace block-level closing tags with newlines for readability
    text = re.sub(r"</(?:p|div|br|h[1-6]|li|tr)>", "\n", html, flags=re.IGNORECASE)
    text = _TAG_RE.sub("", text)
    text = _WHITESPACE_RE.sub("\n\n", text)
    return text.strip()


def _html_to_markdown(html: str) -> str:
    """Best-effort HTML to Markdown conversion using regex.

    Handles headings, paragraphs, bold, italic, and links.  This avoids
    requiring an extra dependency (e.g. html2text) while covering the most
    common EPUB content structures.
    """
    text = html

    # Headings
    for level in range(1, 7):
        tag = f"h{level}"
        prefix = "#" * level
        text = re.sub(
            rf"<{tag}[^>]*>(.*?)</{tag}>",
            rf"\n{prefix} \1\n",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )

    # Bold / italic
    text = re.sub(
        r"<(?:b|strong)[^>]*>(.*?)</(?:b|strong)>",
        r"**\1**",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(
        r"<(?:i|em)[^>]*>(.*?)</(?:i|em)>",
        r"*\1*",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Links
    text = re.sub(
        r'<a[^>]+href="([^"]*)"[^>]*>(.*?)</a>',
        r"[\2](\1)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # List items
    text = re.sub(r"<li[^>]*>", "- ", text, flags=re.IGNORECASE)

    # Paragraphs and line breaks
    text = re.sub(
        r"</(?:p|div|br|li|ul|ol|tr)>",
        "\n",
        text,
        flags=re.IGNORECASE,
    )

    # Strip remaining tags
    text = _TAG_RE.sub("", text)
    text = _WHITESPACE_RE.sub("\n\n", text)
    return text.strip()


def _escape_html(text: str) -> str:
    """Minimal HTML entity escaping for safe insertion into HTML attributes."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
