"""Core abstractions and shared utilities for lazy-splitter.

This package provides the foundation that all media-specific back-ends build
upon: abstract base classes, shared data models, configuration management,
internationalisation helpers, and common utility functions.

Quick import examples::

    from lazy_splitter.core import BaseSplitter, BaseDetector
    from lazy_splitter.core import Chapter, DetectionResult, SplitResult
    from lazy_splitter.core import LazyConfig, load_config
    from lazy_splitter.core import sanitize_filename, detect_file_type
"""

from __future__ import annotations

from lazy_splitter.core.base import (
    BaseConverter,
    BaseDetector,
    BaseMerger,
    BaseSplitter,
)
from lazy_splitter.core.config import (
    LazyConfig,
    get_profile,
    load_config,
    merge_config,
    save_config,
)
from lazy_splitter.core.exceptions import (
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
from lazy_splitter.core.models import (
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
from lazy_splitter.core.utils import (
    atomic_write,
    cleanup_temp_files,
    detect_file_type,
    ensure_dir,
    format_duration,
    format_file_size,
    generate_checksum,
    get_language_patterns,
    get_temp_dir,
    sanitize_filename,
    validate_file,
)

__all__ = [
    # Base classes
    "BaseConverter",
    "BaseDetector",
    "BaseMerger",
    "BaseSplitter",
    # Configuration
    "LazyConfig",
    "get_profile",
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
    # Utilities
    "atomic_write",
    "cleanup_temp_files",
    "detect_file_type",
    "ensure_dir",
    "format_duration",
    "format_file_size",
    "generate_checksum",
    "get_language_patterns",
    "get_temp_dir",
    "sanitize_filename",
    "validate_file",
]
