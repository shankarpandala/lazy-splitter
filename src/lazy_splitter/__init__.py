"""lazy-splitter -- Intelligent file splitting tools for PDFs, videos, audio, and more.

This is the top-level package.  It re-exports the most commonly used symbols
from the :mod:`lazy_splitter.core` sub-package so that users can write concise
imports::

    from lazy_splitter import BaseSplitter, Chapter, DetectionResult
    from lazy_splitter import __version__
"""

from __future__ import annotations

__version__: str = "0.3.0"

# ---------------------------------------------------------------------------
# Convenience re-exports from lazy_splitter.core
# ---------------------------------------------------------------------------

from lazy_splitter.core.base import (  # noqa: E402
    BaseConverter,
    BaseDetector,
    BaseMerger,
    BaseSplitter,
)
from lazy_splitter.core.config import (  # noqa: E402
    LazyConfig,
    load_config,
    merge_config,
    save_config,
)
from lazy_splitter.core.exceptions import (  # noqa: E402
    CloudError,
    ConfigError,
    ConversionError,
    DRMError,
    DetectionError,
    FileTypeError,
    LazySplitterError,
    MergeError,
    PasswordRequiredError,
    PluginError,
    SplitError,
)
from lazy_splitter.core.models import (  # noqa: E402
    AudioSegment,
    Chapter,
    ConversionResult,
    DetectionResult,
    DocumentSection,
    EpubChapter,
    ImageFrame,
    MergeResult,
    SplitResult,
    VideoSegment,
)

__all__ = [
    "__version__",
    # Base classes
    "BaseConverter",
    "BaseDetector",
    "BaseMerger",
    "BaseSplitter",
    # Configuration
    "LazyConfig",
    "load_config",
    "merge_config",
    "save_config",
    # Exceptions
    "CloudError",
    "ConfigError",
    "ConversionError",
    "DRMError",
    "DetectionError",
    "FileTypeError",
    "LazySplitterError",
    "MergeError",
    "PasswordRequiredError",
    "PluginError",
    "SplitError",
    # Models
    "AudioSegment",
    "Chapter",
    "ConversionResult",
    "DetectionResult",
    "DocumentSection",
    "EpubChapter",
    "ImageFrame",
    "MergeResult",
    "SplitResult",
    "VideoSegment",
]
