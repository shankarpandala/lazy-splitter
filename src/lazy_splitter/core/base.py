"""Abstract base classes for detectors, splitters, mergers, and converters.

Every media-specific module (PDF, audio, video, EPUB, etc.) should subclass
the appropriate base class to ensure a consistent public interface across the
entire lazy-splitter toolkit.

Example usage for a new media back-end::

    from lazy_splitter.core.base import BaseDetector, BaseSplitter

    class MyDetector(BaseDetector):
        def detect(self, input_path, strategy="auto", **kwargs):
            ...

    class MySplitter(BaseSplitter):
        @property
        def supported_extensions(self):
            return [".xyz"]

        def split(self, input_path, chapters, **kwargs):
            ...

        def preview(self, input_path, **kwargs):
            ...
"""

from __future__ import annotations

import abc
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

from lazy_splitter.core.models import DetectionResult, SplitResult


# ---------------------------------------------------------------------------
# BaseSplitter
# ---------------------------------------------------------------------------

class BaseSplitter(abc.ABC):
    """Abstract splitter that writes segments / chapters to disk.

    Subclasses **must** implement :meth:`split`, :meth:`preview`, and the
    :attr:`supported_extensions` property.
    """

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or logging.getLogger(self.__class__.__qualname__)

    # -- Abstract interface --------------------------------------------------

    @abc.abstractmethod
    def split(
        self,
        input_path: Path,
        chapters: Sequence[Any],
        **kwargs: Any,
    ) -> List[Path]:
        """Split the file at *input_path* according to *chapters*.

        Parameters:
            input_path: Path to the source file.
            chapters: Sequence of chapter / segment descriptors (media-specific
                dataclasses such as :class:`~lazy_splitter.core.models.Chapter`).
            **kwargs: Format-specific options (output_dir, filename_pattern,
                codec, bitrate, etc.).

        Returns:
            List of :class:`~pathlib.Path` objects pointing to the newly
            created files.

        Raises:
            lazy_splitter.core.exceptions.SplitError:
                If splitting fails for any reason.
        """
        ...  # pragma: no cover

    @abc.abstractmethod
    def preview(
        self,
        input_path: Path,
        **kwargs: Any,
    ) -> DetectionResult:
        """Preview what the splitter would produce without writing files.

        This typically delegates to a detector internally and returns the
        detection result so the user can confirm before proceeding.

        Parameters:
            input_path: Path to the source file.
            **kwargs: Strategy-specific options.

        Returns:
            A :class:`~lazy_splitter.core.models.DetectionResult` describing
            the chapters that would be created.

        Raises:
            lazy_splitter.core.exceptions.DetectionError:
                If detection fails.
        """
        ...  # pragma: no cover

    @property
    @abc.abstractmethod
    def supported_extensions(self) -> List[str]:
        """File extensions this splitter can handle.

        Returns:
            List of extensions including the leading dot, e.g.
            ``[".pdf", ".djvu"]``.
        """
        ...  # pragma: no cover

    # -- Convenience ---------------------------------------------------------

    def can_handle(self, path: Path) -> bool:
        """Return whether this splitter supports the file at *path*.

        The default implementation checks the file extension against
        :attr:`supported_extensions`.  Subclasses may override to add
        magic-byte detection or other heuristics.

        Parameters:
            path: Path to the file to check.

        Returns:
            ``True`` if this splitter can process the file.
        """
        return path.suffix.lower() in {ext.lower() for ext in self.supported_extensions}


# ---------------------------------------------------------------------------
# BaseDetector
# ---------------------------------------------------------------------------

class BaseDetector(abc.ABC):
    """Abstract detector that locates chapter / segment boundaries.

    Subclasses **must** implement :meth:`detect` with the concrete detection
    logic for a given media type.
    """

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or logging.getLogger(self.__class__.__qualname__)

    @abc.abstractmethod
    def detect(
        self,
        input_path: Path,
        strategy: str = "auto",
        **kwargs: Any,
    ) -> DetectionResult:
        """Detect chapters or segments in the file at *input_path*.

        Parameters:
            input_path: Path to the source file.
            strategy: Name of the detection strategy (e.g. ``"toc"``,
                ``"bookmarks"``, ``"silence"``, ``"scene"``, ``"auto"``).
            **kwargs: Strategy-specific options.

        Returns:
            A :class:`~lazy_splitter.core.models.DetectionResult` containing
            the detected segments and metadata.

        Raises:
            lazy_splitter.core.exceptions.DetectionError:
                If detection fails for any reason.
        """
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# BaseMerger
# ---------------------------------------------------------------------------

class BaseMerger(abc.ABC):
    """Abstract merger that combines multiple files into one.

    Subclasses **must** implement :meth:`merge`.
    """

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or logging.getLogger(self.__class__.__qualname__)

    @abc.abstractmethod
    def merge(
        self,
        input_paths: List[Path],
        output_path: Path,
        **kwargs: Any,
    ) -> Path:
        """Merge *input_paths* into a single file at *output_path*.

        Parameters:
            input_paths: Ordered list of files to merge.
            output_path: Destination path for the merged output.
            **kwargs: Format-specific options (codec, metadata, etc.).

        Returns:
            Path to the created output file (same as *output_path* on success).

        Raises:
            lazy_splitter.core.exceptions.MergeError:
                If the merge operation fails.
        """
        ...  # pragma: no cover

    # -- Convenience ---------------------------------------------------------

    def _validate_inputs(self, paths: Sequence[Path]) -> List[Path]:
        """Validate that all *paths* exist and are files.

        Returns the validated list so subclasses can do::

            validated = self._validate_inputs(paths)

        Raises:
            lazy_splitter.core.exceptions.MergeError:
                If any path is missing or is not a regular file.
        """
        from lazy_splitter.core.exceptions import MergeError

        validated: List[Path] = []
        for p in paths:
            p = Path(p)
            if not p.exists():
                raise MergeError("Input file does not exist", path=str(p))
            if not p.is_file():
                raise MergeError("Input path is not a file", path=str(p))
            validated.append(p)

        if len(validated) < 1:
            raise MergeError("At least one input file is required")
        return validated


# ---------------------------------------------------------------------------
# BaseConverter
# ---------------------------------------------------------------------------

class BaseConverter(abc.ABC):
    """Abstract converter that transforms a file from one format to another.

    Subclasses **must** implement :meth:`convert` and the
    :attr:`supported_conversions` property.
    """

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or logging.getLogger(self.__class__.__qualname__)

    @abc.abstractmethod
    def convert(
        self,
        input_path: Path,
        output_path: Path,
        output_format: str,
        **kwargs: Any,
    ) -> Path:
        """Convert the file at *input_path* to *output_format*.

        Parameters:
            input_path: Path to the source file.
            output_path: Destination path for the converted file.
            output_format: Target format identifier (e.g. ``"epub"``,
                ``"mp3"``, ``"png"``).
            **kwargs: Conversion-specific options (quality, codec, DPI, etc.).

        Returns:
            Path to the created output file (same as *output_path* on success).

        Raises:
            lazy_splitter.core.exceptions.ConversionError:
                If conversion fails.
        """
        ...  # pragma: no cover

    @property
    @abc.abstractmethod
    def supported_conversions(self) -> List[Tuple[str, str]]:
        """Supported (input_format, output_format) pairs.

        Returns:
            List of 2-tuples, e.g. ``[("pdf", "epub"), ("pdf", "docx")]``.
        """
        ...  # pragma: no cover

    # -- Convenience ---------------------------------------------------------

    def can_convert(self, input_format: str, output_format: str) -> bool:
        """Check whether this converter supports the given format pair.

        Parameters:
            input_format: Source format string.
            output_format: Target format string.

        Returns:
            ``True`` if the conversion is supported.
        """
        return (input_format.lower(), output_format.lower()) in {
            (a.lower(), b.lower()) for a, b in self.supported_conversions
        }

    def _validate_input(self, path: Path) -> Path:
        """Validate that *path* exists and is a file.

        Returns the validated path so subclasses can do::

            validated = self._validate_input(path)

        Raises:
            lazy_splitter.core.exceptions.ConversionError:
                If the path is missing or is not a regular file.
        """
        from lazy_splitter.core.exceptions import ConversionError

        p = Path(path) if not isinstance(path, Path) else path
        if not p.exists():
            raise ConversionError("Input file does not exist", path=str(p))
        if not p.is_file():
            raise ConversionError("Input path is not a file", path=str(p))
        return p
