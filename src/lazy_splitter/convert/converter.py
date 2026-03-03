"""Top-level format converter that auto-dispatches to specialised back-ends.

:class:`FormatConverter` inspects the input and output formats and delegates
the actual work to :class:`~lazy_splitter.convert.document_converter.DocumentConverter`
or :class:`~lazy_splitter.convert.media_converter.MediaConverter` as appropriate.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from lazy_splitter.core.exceptions import ConversionError
from lazy_splitter.core.models import ConversionResult
from lazy_splitter.core.utils import ensure_dir

from lazy_splitter.convert.document_converter import DocumentConverter
from lazy_splitter.convert.media_converter import MediaConverter
from lazy_splitter.convert.models import CONVERSION_MAP

logger = logging.getLogger(__name__)


class FormatConverter:
    """Unified entry-point for all format conversions.

    The converter maintains instances of the specialised back-ends and
    dispatches to the correct one based on the input/output format pair.

    Example::

        converter = FormatConverter()
        result_path = converter.convert(
            Path("book.pdf"),
            Path("book.txt"),
            output_format="txt",
        )
    """

    def __init__(self, logger_: Optional[logging.Logger] = None) -> None:
        self._logger = logger_ or logging.getLogger(self.__class__.__qualname__)
        self._document_converter = DocumentConverter(logger=self._logger)
        self._media_converter = MediaConverter(logger=self._logger)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def convert(
        self,
        input_path: Path,
        output_path: Path,
        output_format: str,
        **kwargs: Any,
    ) -> Path:
        """Convert *input_path* to *output_format*, writing the result to *output_path*.

        The method inspects the input extension and *output_format* to decide
        which specialised converter to invoke.

        Parameters
        ----------
        input_path:
            Path to the source file.
        output_path:
            Destination path for the converted file (or directory for
            multi-file outputs such as PDF-to-images).
        output_format:
            Target format identifier, e.g. ``"png"``, ``"mp3"``, ``"html"``.
        **kwargs:
            Conversion-specific options forwarded to the underlying converter
            (``quality``, ``dpi``, ``codec``, ``bitrate``, ``fps``, ``width``).

        Returns
        -------
        Path
            Path to the primary output file.

        Raises
        ------
        ConversionError
            If the conversion is unsupported or fails.
        """
        input_path = Path(input_path)
        output_path = Path(output_path)
        out_fmt = output_format.lower().lstrip(".")

        if not input_path.is_file():
            raise ConversionError(
                "Input file does not exist or is not a file",
                path=str(input_path),
            )

        in_ext = input_path.suffix.lower().lstrip(".")

        # Validate the conversion is in our map
        supported_outputs = CONVERSION_MAP.get(in_ext)
        if supported_outputs is None:
            raise ConversionError(
                f"No conversions available for input format: {in_ext!r}",
                input_format=in_ext,
            )
        if out_fmt not in supported_outputs:
            raise ConversionError(
                f"Conversion from {in_ext!r} to {out_fmt!r} is not supported. "
                f"Supported targets: {supported_outputs}",
                input_format=in_ext,
                output_format=out_fmt,
            )

        ensure_dir(output_path.parent)

        t0 = time.monotonic()

        # Dispatch to the correct back-end
        converter = self._select_converter(in_ext, out_fmt)
        result = converter.convert(
            input_path, output_path, output_format=out_fmt, **kwargs
        )

        elapsed = time.monotonic() - t0
        self._logger.info(
            "Conversion %s -> %s completed in %.2fs: %s",
            in_ext,
            out_fmt,
            elapsed,
            result,
        )
        return result

    @staticmethod
    def get_supported_conversions() -> Dict[str, List[str]]:
        """Return the full map of input formats to possible output formats.

        Returns
        -------
        dict
            A copy of :data:`~lazy_splitter.convert.models.CONVERSION_MAP`,
            mapping each input extension (without dot) to a list of supported
            output extensions (without dot).

        Example::

            >>> FormatConverter.get_supported_conversions()["pdf"]
            ['png', 'jpeg', 'jpg', 'tiff', 'bmp', 'txt', 'text']
        """
        return {k: list(v) for k, v in CONVERSION_MAP.items()}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _select_converter(
        self, in_ext: str, out_ext: str,
    ) -> Any:
        """Choose the appropriate converter back-end for the given format pair.

        Parameters
        ----------
        in_ext:
            Input format extension (lowercase, no dot).
        out_ext:
            Output format extension (lowercase, no dot).

        Returns
        -------
        DocumentConverter or MediaConverter
            The converter instance to use.

        Raises
        ------
        ConversionError
            If no back-end supports the format pair.
        """
        # Check document converter first
        if self._document_converter.can_convert(in_ext, out_ext):
            return self._document_converter

        # Then media converter
        if self._media_converter.can_convert(in_ext, out_ext):
            return self._media_converter

        raise ConversionError(
            f"No converter back-end found for {in_ext!r} -> {out_ext!r}",
            input_format=in_ext,
            output_format=out_ext,
        )
