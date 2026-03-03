"""Custom exception hierarchy for lazy-splitter.

All exceptions inherit from :class:`LazySplitterError` so that callers can
catch a single base class when they want blanket error handling, while still
being able to react to specific failure modes.
"""

from __future__ import annotations


class LazySplitterError(Exception):
    """Base exception for all lazy-splitter errors.

    Attributes:
        message: Human-readable description of the error.
        details: Optional mapping of additional context (paths, formats, etc.).
    """

    def __init__(self, message: str, **details: object) -> None:
        self.message = message
        self.details = details
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover
        if self.details:
            extra = ", ".join(f"{k}={v!r}" for k, v in self.details.items())
            return f"{self.message} ({extra})"
        return self.message


# ---------------------------------------------------------------------------
# File & format errors
# ---------------------------------------------------------------------------

class FileTypeError(LazySplitterError):
    """Raised when a file's type is unsupported or does not match expectations.

    Examples:
        * Attempting to split a JPEG with the PDF splitter.
        * A file whose extension does not match its detected MIME type.
    """


class PasswordRequiredError(LazySplitterError):
    """Raised when a file is password-protected and no password was supplied."""


class DRMError(LazySplitterError):
    """Raised when a file is protected by DRM and cannot be processed."""


# ---------------------------------------------------------------------------
# Processing errors
# ---------------------------------------------------------------------------

class DetectionError(LazySplitterError):
    """Raised when chapter / segment detection fails.

    This may happen due to corrupt files, unsupported internal structures, or
    when no chapters can be detected even with fallback strategies.
    """


class SplitError(LazySplitterError):
    """Raised when a splitting operation fails.

    Common causes include I/O errors during file creation, insufficient disk
    space, or internal library failures.
    """


class MergeError(LazySplitterError):
    """Raised when a merge operation fails.

    For example, merging files with incompatible formats or corrupt inputs.
    """


class ConversionError(LazySplitterError):
    """Raised when a file conversion fails.

    This may occur when the target format is unsupported, required codecs are
    missing, or the source file is corrupt.
    """


# ---------------------------------------------------------------------------
# Infrastructure errors
# ---------------------------------------------------------------------------

class ConfigError(LazySplitterError):
    """Raised for configuration-related problems.

    Examples:
        * Malformed TOML configuration file.
        * Unknown profile name.
        * Invalid configuration value.
    """


class PluginError(LazySplitterError):
    """Raised when a plugin fails to load or execute.

    This covers missing entry-points, incompatible plugin API versions, and
    runtime errors within plugin code.
    """


class CloudError(LazySplitterError):
    """Raised when a cloud storage operation fails.

    Covers authentication failures, network errors, quota exhaustion, and
    provider-specific API errors.
    """
