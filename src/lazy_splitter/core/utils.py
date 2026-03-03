"""Shared utility helpers used across all lazy-splitter modules.

This module collects small, reusable functions that do not depend on any
media-specific library so they can be safely imported from anywhere in the
project.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set

from lazy_splitter.core.exceptions import FileTypeError

# ---------------------------------------------------------------------------
# File-name helpers
# ---------------------------------------------------------------------------

#: Characters that are invalid on one or more common file systems.
_INVALID_FILENAME_CHARS: str = r'<>:"/\|?*'

#: Control characters (ASCII 0-31) are forbidden on Windows.
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f]")


def sanitize_filename(title: str, max_length: int = 100) -> str:
    """Sanitize *title* so it is safe to use as a file-name component.

    Parameters:
        title: The raw string (e.g. a chapter title).
        max_length: Maximum length for the returned string.

    Returns:
        A filesystem-safe string with no leading/trailing whitespace or
        underscores, no control characters, and no runs of consecutive
        underscores.
    """
    name = title

    # Strip control characters
    name = _CONTROL_CHAR_RE.sub("", name)

    # Replace invalid characters with underscores
    for ch in _INVALID_FILENAME_CHARS:
        name = name.replace(ch, "_")

    # Collapse runs of whitespace and underscores
    name = re.sub(r"[\s_]+", "_", name)
    name = name.strip("_. ")

    # Truncate while avoiding a trailing underscore
    if len(name) > max_length:
        name = name[:max_length].rstrip("_. ")

    return name or "untitled"


# ---------------------------------------------------------------------------
# File-type detection
# ---------------------------------------------------------------------------

#: Mapping from common extensions to canonical type strings.
_EXTENSION_MAP: Dict[str, str] = {
    ".pdf": "pdf",
    ".epub": "epub",
    ".mobi": "mobi",
    ".azw": "mobi",
    ".azw3": "mobi",
    ".djvu": "djvu",
    ".djv": "djvu",
    ".docx": "docx",
    ".doc": "doc",
    ".odt": "odt",
    ".rtf": "rtf",
    ".txt": "text",
    ".md": "markdown",
    ".html": "html",
    ".htm": "html",
    ".xml": "xml",
    ".mp4": "video",
    ".mkv": "video",
    ".avi": "video",
    ".mov": "video",
    ".webm": "video",
    ".flv": "video",
    ".wmv": "video",
    ".mp3": "audio",
    ".flac": "audio",
    ".wav": "audio",
    ".ogg": "audio",
    ".m4a": "audio",
    ".aac": "audio",
    ".wma": "audio",
    ".opus": "audio",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".gif": "image",
    ".bmp": "image",
    ".tiff": "image",
    ".tif": "image",
    ".webp": "image",
    ".svg": "image",
    ".cbz": "comic",
    ".cbr": "comic",
    ".cb7": "comic",
}

#: Magic-byte signatures for common formats (offset, bytes, type).
_MAGIC_SIGNATURES: List[tuple] = [
    (0, b"%PDF", "pdf"),
    (0, b"PK\x03\x04", "zip"),  # EPUB / DOCX / ODT are ZIP-based
    (0, b"\x00\x00\x00\x1cftyp", "video"),
    (0, b"\x1a\x45\xdf\xa3", "video"),  # Matroska / WebM
    (0, b"RIFF", "audio"),  # WAV
    (0, b"fLaC", "audio"),  # FLAC
    (0, b"ID3", "audio"),   # MP3 with ID3
    (0, b"\xff\xfb", "audio"),  # MP3 without ID3
    (0, b"OggS", "audio"),  # OGG
    (0, b"\x89PNG", "image"),
    (0, b"\xff\xd8\xff", "image"),  # JPEG
    (0, b"GIF8", "image"),
    (0, b"AT&TFORM", "djvu"),
]


def detect_file_type(path: str | Path) -> str:
    """Detect the file type from extension and, where possible, magic bytes.

    The extension check is performed first; if the extension is unknown the
    function falls back to reading the first few bytes of the file.

    Parameters:
        path: Path to the file.

    Returns:
        A canonical type string such as ``"pdf"``, ``"epub"``, ``"video"``,
        ``"audio"``, ``"image"``, etc.

    Raises:
        FileTypeError: When the file type cannot be determined.
    """
    p = Path(path)

    # 1. Extension-based detection
    ext = p.suffix.lower()
    if ext in _EXTENSION_MAP:
        return _EXTENSION_MAP[ext]

    # 2. Magic-byte detection
    try:
        with open(p, "rb") as fh:
            header = fh.read(32)
        for offset, magic, file_type in _MAGIC_SIGNATURES:
            if header[offset:offset + len(magic)] == magic:
                return file_type
    except OSError:
        pass

    raise FileTypeError(
        f"Unable to determine file type for {p.name}",
        path=str(p),
    )


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def format_duration(seconds: float) -> str:
    """Format a duration in seconds into a human-friendly string.

    Parameters:
        seconds: Duration in seconds (non-negative).

    Returns:
        A string such as ``"1h 23m 45s"``, ``"5m 12s"``, ``"3s"``, or
        ``"0.45s"`` for sub-second durations.
    """
    if seconds < 0:
        seconds = 0.0

    if seconds < 1:
        return f"{seconds:.2f}s"

    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)

    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def format_file_size(size_bytes: int) -> str:
    """Format a byte count into a human-friendly string.

    Parameters:
        size_bytes: Size in bytes (non-negative).

    Returns:
        A string such as ``"1.23 MB"``, ``"456 KB"``, or ``"78 B"``.
    """
    if size_bytes < 0:
        size_bytes = 0

    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{size_bytes} {unit}"
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0  # type: ignore[assignment]

    # Unreachable, but keeps mypy happy
    return f"{size_bytes:.2f} TB"  # pragma: no cover


# ---------------------------------------------------------------------------
# Checksums
# ---------------------------------------------------------------------------

def generate_checksum(path: str | Path, algorithm: str = "sha256") -> str:
    """Generate a hex-digest checksum for the file at *path*.

    Parameters:
        path: Path to the file to hash.
        algorithm: Any algorithm name accepted by :mod:`hashlib` (e.g.
            ``"sha256"``, ``"md5"``, ``"sha1"``).

    Returns:
        The hex-encoded digest string.

    Raises:
        ValueError: If *algorithm* is not supported.
        OSError: If the file cannot be read.
    """
    try:
        h = hashlib.new(algorithm)
    except ValueError:
        raise ValueError(
            f"Unsupported hash algorithm {algorithm!r}. "
            f"Available: {sorted(hashlib.algorithms_available)}"
        )

    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            h.update(chunk)

    return h.hexdigest()


# ---------------------------------------------------------------------------
# Directory / temp-file helpers
# ---------------------------------------------------------------------------

def ensure_dir(path: str | Path) -> Path:
    """Create *path* (and parents) if it does not exist, then return it.

    Parameters:
        path: Directory path to ensure.

    Returns:
        The same *path* as a :class:`Path` for convenient chaining.
    """
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


@contextlib.contextmanager
def atomic_write(path: str | Path, mode: str = "wb") -> Iterator[Any]:
    """Context manager that writes to a temporary file and renames on success.

    This prevents half-written files if the process crashes mid-write.

    Parameters:
        path: Destination file path.
        mode: File open mode (``"wb"`` for binary, ``"w"`` for text).

    Yields:
        An open file object.  The caller should write to it; on successful
        exit the temporary file is atomically moved to *path*.

    Example::

        with atomic_write("output.pdf") as f:
            f.write(data)
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=str(dest.parent),
        prefix=".lazy_tmp_",
        suffix=dest.suffix,
    )
    try:
        with os.fdopen(fd, mode) as fh:
            yield fh
        # Atomic rename (same filesystem)
        shutil.move(tmp_path, str(dest))
    except BaseException:
        # Clean up on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def get_temp_dir() -> Path:
    """Return a temporary directory for lazy-splitter operations.

    The directory is created inside the system temp area under a
    ``lazy-splitter`` sub-folder.

    Returns:
        Path to the temporary directory (created if it did not exist).
    """
    tmp = Path(tempfile.gettempdir()) / "lazy-splitter"
    tmp.mkdir(parents=True, exist_ok=True)
    return tmp


def cleanup_temp_files(temp_dir: str | Path) -> None:
    """Remove all contents of *temp_dir* created by lazy-splitter.

    If *temp_dir* does not exist the call is a no-op.

    Parameters:
        temp_dir: Path to the temporary directory to clean.
    """
    p = Path(temp_dir)
    if p.is_dir():
        shutil.rmtree(p, ignore_errors=True)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_EXPECTED_TYPES_MAP: Dict[str, Set[str]] = {
    "pdf": {".pdf"},
    "epub": {".epub"},
    "video": {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv"},
    "audio": {".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".wma", ".opus"},
    "image": {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".webp", ".svg"},
    "document": {".docx", ".doc", ".odt", ".rtf", ".txt", ".md", ".html", ".htm"},
}


def validate_file(path: str | Path, expected_types: Optional[List[str]] = None) -> bool:
    """Validate that *path* exists, is readable, and optionally matches expected types.

    Parameters:
        path: Path to the file.
        expected_types: Optional list of canonical type strings (e.g.
            ``["pdf", "epub"]``).  If provided the file's extension must match
            one of the given types.

    Returns:
        ``True`` if the file passes all checks.

    Raises:
        FileNotFoundError: If the file does not exist.
        PermissionError: If the file is not readable.
        FileTypeError: If *expected_types* is given and the file does not match.
    """
    p = Path(path)

    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")

    if not os.access(p, os.R_OK):
        raise PermissionError(f"File is not readable: {p}")

    if expected_types is not None:
        ext = p.suffix.lower()
        allowed: Set[str] = set()
        for t in expected_types:
            allowed |= _EXPECTED_TYPES_MAP.get(t, {f".{t}"})
        if ext not in allowed:
            raise FileTypeError(
                f"File type {ext!r} not in expected types {sorted(allowed)}",
                path=str(p),
                expected=expected_types,
            )

    return True


# ---------------------------------------------------------------------------
# Language / chapter patterns (thin wrapper around i18n module)
# ---------------------------------------------------------------------------

def get_language_patterns(language: Optional[str] = None) -> Dict[str, Any]:
    """Return chapter heading patterns for the given language.

    This is a convenience wrapper around :func:`lazy_splitter.core.i18n.get_patterns`
    that returns a dictionary containing both the language code used and the
    list of regex pattern strings.

    Parameters:
        language: Two-letter ISO 639-1 code, or *None* to auto-detect.

    Returns:
        A dictionary with keys ``"language"`` and ``"patterns"``.
    """
    # Import lazily to avoid circular imports in edge cases
    from lazy_splitter.core.i18n import get_patterns, _detect_system_language

    if language is None:
        language = _detect_system_language()

    patterns = get_patterns(language)
    return {
        "language": language,
        "patterns": patterns,
    }
