"""OCR text extraction engine for lazy-splitter.

This module provides the :class:`OCREngine` class which wraps multiple OCR
backends for extracting text from images and PDF files:

* **Tesseract** – via the *pytesseract* Python wrapper around the Tesseract
  OCR engine (requires the ``tesseract`` system binary).
* **EasyOCR** – via the *easyocr* Python library (GPU-accelerated when CUDA
  is available).
* **Auto** – automatically selects the best available engine.

All external libraries are imported lazily inside the methods that need them
so the module can be imported even when optional dependencies are absent.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from lazy_splitter.ai.models import OCRResult
from lazy_splitter.core.exceptions import DetectionError, LazySplitterError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supported engines
# ---------------------------------------------------------------------------

_SUPPORTED_ENGINES = frozenset({"tesseract", "easyocr", "auto"})


# ---------------------------------------------------------------------------
# OCREngine
# ---------------------------------------------------------------------------

class OCREngine:
    """Extract text from images and PDF pages using OCR.

    Parameters
    ----------
    custom_logger:
        Optional :class:`logging.Logger` instance.  If *None*, a module-level
        logger is used.

    Examples
    --------
    >>> engine = OCREngine()
    >>> result = engine.extract_text("scan.png", engine="tesseract")
    >>> print(result.text)
    """

    def __init__(self, custom_logger: Optional[logging.Logger] = None) -> None:
        self.logger = custom_logger or logger

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_text(
        self,
        image_or_pdf_path: str,
        engine: str = "auto",
        language: str = "eng",
    ) -> OCRResult:
        """Extract text from a single image or PDF file.

        For PDFs the first page is extracted.  Use :meth:`extract_pages` to
        process every page individually.

        Parameters
        ----------
        image_or_pdf_path:
            Path to an image (PNG, JPEG, TIFF, BMP) or a single-page PDF.
        engine:
            OCR engine – ``"tesseract"``, ``"easyocr"``, or ``"auto"``.
        language:
            Language code.  For Tesseract this is a Tesseract lang code
            (e.g. ``"eng"``); for EasyOCR pass the corresponding ISO code
            (e.g. ``"en"``).

        Returns
        -------
        OCRResult
            Extraction result containing the recognised text and metadata.

        Raises
        ------
        DetectionError
            If the engine is unknown, the file does not exist, or OCR fails.
        """
        path = Path(image_or_pdf_path)
        self._validate_path(path)
        engine = self._resolve_engine(engine)

        start = time.monotonic()

        if path.suffix.lower() == ".pdf":
            text = self._ocr_pdf_first_page(path, engine, language)
        elif engine == "tesseract":
            text = self.extract_text_tesseract(str(path), language)
        else:
            langs = self._tesseract_lang_to_easyocr(language)
            text = self.extract_text_easyocr(str(path), langs)

        elapsed = time.monotonic() - start

        return OCRResult(
            text=text,
            confidence=self.get_confidence(str(path)) if text.strip() else 0.0,
            language_detected=language,
            engine_used=engine,
            metadata={
                "source_path": str(path),
                "processing_time": round(elapsed, 3),
            },
        )

    def extract_text_tesseract(
        self,
        image_path: str,
        language: str = "eng",
    ) -> str:
        """Extract text from an image using Tesseract OCR.

        Parameters
        ----------
        image_path:
            Path to the image file.
        language:
            Tesseract language code (e.g. ``"eng"``, ``"fra"``, ``"deu"``).

        Returns
        -------
        str
            The recognised plain text.

        Raises
        ------
        DetectionError
            If *pytesseract* or *Pillow* is not installed, or OCR fails.
        """
        try:
            import pytesseract  # type: ignore[import-untyped]
        except ImportError:
            raise DetectionError(
                "The 'pytesseract' package is required for Tesseract OCR. "
                "Install it with: pip install pytesseract  "
                "(also ensure the 'tesseract' binary is on your PATH)"
            )

        try:
            from PIL import Image  # type: ignore[import-untyped]
        except ImportError:
            raise DetectionError(
                "The 'Pillow' package is required for image handling. "
                "Install it with: pip install Pillow"
            )

        self.logger.info("Running Tesseract OCR on %s (lang=%s)", image_path, language)
        try:
            img = Image.open(image_path)
            text: str = pytesseract.image_to_string(img, lang=language)
            return text
        except Exception as exc:
            raise DetectionError(
                f"Tesseract OCR failed on {image_path}: {exc}",
                engine="tesseract",
                path=image_path,
            ) from exc

    def extract_text_easyocr(
        self,
        image_path: str,
        languages: Optional[List[str]] = None,
    ) -> str:
        """Extract text from an image using EasyOCR.

        Parameters
        ----------
        image_path:
            Path to the image file.
        languages:
            List of language codes (e.g. ``["en"]``, ``["en", "fr"]``).
            Defaults to ``["en"]``.

        Returns
        -------
        str
            The recognised plain text (results joined by newlines).

        Raises
        ------
        DetectionError
            If *easyocr* is not installed or OCR fails.
        """
        try:
            import easyocr  # type: ignore[import-untyped]
        except ImportError:
            raise DetectionError(
                "The 'easyocr' package is required for EasyOCR. "
                "Install it with: pip install easyocr"
            )

        if languages is None:
            languages = ["en"]

        self.logger.info(
            "Running EasyOCR on %s (languages=%s)", image_path, languages,
        )
        try:
            reader = easyocr.Reader(languages, verbose=False)
            results = reader.readtext(image_path, detail=0)
            return "\n".join(str(line) for line in results)
        except Exception as exc:
            raise DetectionError(
                f"EasyOCR failed on {image_path}: {exc}",
                engine="easyocr",
                path=image_path,
            ) from exc

    def extract_pages(
        self,
        pdf_path: str,
        engine: str = "auto",
        language: str = "eng",
    ) -> List[str]:
        """OCR each page of a PDF and return a list of per-page text strings.

        Parameters
        ----------
        pdf_path:
            Path to the PDF file.
        engine:
            OCR engine – ``"tesseract"``, ``"easyocr"``, or ``"auto"``.
        language:
            Language code appropriate for the selected engine.

        Returns
        -------
        list[str]
            One string per page, in document order.

        Raises
        ------
        DetectionError
            If *pdf2image* is not installed, the PDF cannot be converted, or
            OCR fails.
        """
        try:
            from pdf2image import convert_from_path  # type: ignore[import-untyped]
        except ImportError:
            raise DetectionError(
                "The 'pdf2image' package is required for PDF page OCR. "
                "Install it with: pip install pdf2image  "
                "(also ensure 'poppler-utils' is installed on your system)"
            )

        path = Path(pdf_path)
        self._validate_path(path)
        engine = self._resolve_engine(engine)

        self.logger.info("Converting PDF pages to images: %s", pdf_path)
        try:
            images = convert_from_path(str(path))
        except Exception as exc:
            raise DetectionError(
                f"Failed to convert PDF to images: {exc}",
                path=pdf_path,
            ) from exc

        page_texts: List[str] = []
        for i, img in enumerate(images):
            self.logger.debug("OCR page %d/%d", i + 1, len(images))
            try:
                text = self._ocr_pil_image(img, engine, language)
                page_texts.append(text)
            except Exception as exc:
                self.logger.warning("OCR failed on page %d: %s", i + 1, exc)
                page_texts.append("")

        return page_texts

    def get_confidence(self, image_path: str) -> float:
        """Return an overall OCR confidence score for the given image.

        The score is computed using Tesseract's per-word confidence data.
        If Tesseract is not available, a default score of ``0.0`` is returned.

        Parameters
        ----------
        image_path:
            Path to the image file.

        Returns
        -------
        float
            Average confidence in the range ``[0.0, 1.0]``.
        """
        try:
            import pytesseract  # type: ignore[import-untyped]
            from PIL import Image  # type: ignore[import-untyped]
        except ImportError:
            self.logger.debug(
                "pytesseract/Pillow not available; returning default confidence 0.0"
            )
            return 0.0

        try:
            img = Image.open(image_path)
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            confidences = [
                int(c) for c in data.get("conf", []) if str(c).lstrip("-").isdigit() and int(c) >= 0
            ]
            if not confidences:
                return 0.0
            return round(sum(confidences) / len(confidences) / 100.0, 3)
        except Exception as exc:
            self.logger.debug("Confidence estimation failed: %s", exc)
            return 0.0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_path(path: Path) -> None:
        """Raise :class:`DetectionError` if *path* does not exist."""
        if not path.exists():
            raise DetectionError(
                f"File not found: {path}", path=str(path),
            )
        if not path.is_file():
            raise DetectionError(
                f"Path is not a regular file: {path}", path=str(path),
            )

    def _resolve_engine(self, engine: str) -> str:
        """Normalise *engine* and, for ``"auto"``, pick the best available."""
        engine = engine.lower().strip()
        if engine not in _SUPPORTED_ENGINES:
            raise DetectionError(
                f"Unknown OCR engine {engine!r}. "
                f"Choose from: {', '.join(sorted(_SUPPORTED_ENGINES))}",
                engine=engine,
            )

        if engine != "auto":
            return engine

        # Auto-select: prefer Tesseract (faster, lighter), fall back to EasyOCR.
        try:
            import pytesseract  # type: ignore[import-untyped] # noqa: F401
            return "tesseract"
        except ImportError:
            pass

        try:
            import easyocr  # type: ignore[import-untyped] # noqa: F401
            return "easyocr"
        except ImportError:
            pass

        raise DetectionError(
            "No OCR engine is available. Install one of:\n"
            "  pip install pytesseract   (+ Tesseract binary)\n"
            "  pip install easyocr"
        )

    def _ocr_pil_image(
        self,
        img: Any,
        engine: str,
        language: str,
    ) -> str:
        """Run OCR on an already-opened PIL Image object."""
        if engine == "tesseract":
            try:
                import pytesseract  # type: ignore[import-untyped]
            except ImportError:
                raise DetectionError(
                    "pytesseract is required but not installed."
                )
            return str(pytesseract.image_to_string(img, lang=language))

        # EasyOCR path – requires saving to a temporary file.
        import tempfile

        try:
            import easyocr  # type: ignore[import-untyped]
        except ImportError:
            raise DetectionError("easyocr is required but not installed.")

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
            img.save(tmp_path, format="PNG")

        try:
            langs = self._tesseract_lang_to_easyocr(language)
            reader = easyocr.Reader(langs, verbose=False)
            results = reader.readtext(tmp_path, detail=0)
            return "\n".join(str(line) for line in results)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _ocr_pdf_first_page(
        self,
        path: Path,
        engine: str,
        language: str,
    ) -> str:
        """Convert the first page of a PDF to an image and OCR it."""
        try:
            from pdf2image import convert_from_path  # type: ignore[import-untyped]
        except ImportError:
            raise DetectionError(
                "The 'pdf2image' package is required for PDF OCR. "
                "Install it with: pip install pdf2image"
            )

        try:
            images = convert_from_path(str(path), first_page=1, last_page=1)
        except Exception as exc:
            raise DetectionError(
                f"Failed to render PDF page: {exc}", path=str(path),
            ) from exc

        if not images:
            return ""
        return self._ocr_pil_image(images[0], engine, language)

    @staticmethod
    def _tesseract_lang_to_easyocr(lang: str) -> List[str]:
        """Best-effort conversion from a Tesseract lang code to EasyOCR codes.

        Tesseract uses three-letter codes (``eng``, ``fra``, ``deu``, ...),
        while EasyOCR uses two-letter ISO 639-1 codes (``en``, ``fr``, ``de``).
        """
        _MAP: Dict[str, str] = {
            "eng": "en",
            "fra": "fr",
            "deu": "de",
            "spa": "es",
            "ita": "it",
            "por": "pt",
            "nld": "nl",
            "rus": "ru",
            "chi_sim": "ch_sim",
            "chi_tra": "ch_tra",
            "jpn": "ja",
            "kor": "ko",
            "ara": "ar",
            "hin": "hi",
        }
        if lang in _MAP:
            return [_MAP[lang]]
        # If the code is already two letters, pass it through.
        if len(lang) == 2:
            return [lang]
        # Fallback: use the first two characters.
        return [lang[:2]]
