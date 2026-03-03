"""Conversion-specific data models and format mapping tables.

Provides :class:`ConversionOptions` for controlling quality, resolution, and
codec parameters, as well as :data:`CONVERSION_MAP` — the authoritative
registry of supported input-to-output format conversions.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, List, Optional


@dataclasses.dataclass
class ConversionOptions:
    """Options that govern how a conversion is performed.

    All fields are optional; converters fall back to sensible defaults when
    a value is ``None``.

    Attributes
    ----------
    quality:
        Quality level for lossy encodings.  Interpretation is
        format-specific (e.g. JPEG quality 1-100, CRF for video).
    dpi:
        Resolution in dots-per-inch for rasterisation (PDF -> image, etc.).
    codec:
        Explicit video / audio codec name (e.g. ``"libx264"``, ``"aac"``).
    bitrate:
        Target bitrate string understood by FFmpeg (e.g. ``"192k"``,
        ``"2M"``).
    sample_rate:
        Audio sample rate in Hz (e.g. ``44100``, ``48000``).
    image_format:
        Target image format when rasterising pages (``"png"``, ``"jpeg"``).
    fps:
        Frames-per-second for GIF / video output.
    width:
        Target width in pixels (height is inferred to keep aspect ratio).
    extra:
        Catch-all for converter-specific options not covered above.
    """

    quality: Optional[int] = None
    dpi: Optional[int] = None
    codec: Optional[str] = None
    bitrate: Optional[str] = None
    sample_rate: Optional[int] = None
    image_format: Optional[str] = None
    fps: Optional[int] = None
    width: Optional[int] = None
    extra: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def merge(self, overrides: Dict[str, Any]) -> "ConversionOptions":
        """Return a *new* instance with non-``None`` values from *overrides*.

        Unknown keys are silently placed into :attr:`extra`.

        Parameters
        ----------
        overrides:
            Mapping of option names to values.

        Returns
        -------
        ConversionOptions
            A fresh copy with the merged values.
        """
        known_fields = {f.name for f in dataclasses.fields(self)}
        updates: Dict[str, Any] = {}
        extra = dict(self.extra)
        for key, value in overrides.items():
            if value is None:
                continue
            if key in known_fields and key != "extra":
                updates[key] = value
            else:
                extra[key] = value
        merged = dataclasses.replace(self, **updates)
        # Manually set extra since dataclasses.replace would overwrite it.
        object.__setattr__(merged, "extra", extra)
        return merged


# ---------------------------------------------------------------------------
# Supported conversion mapping
# ---------------------------------------------------------------------------

#: Authoritative map of input file extensions to lists of supported output
#: extensions.  Extensions are stored *without* a leading dot and in
#: lower-case.  Converters use this map to validate requests and to
#: advertise capabilities.
CONVERSION_MAP: Dict[str, List[str]] = {
    # ── Document conversions ──────────────────────────────────────────
    "pdf": ["png", "jpeg", "jpg", "tiff", "bmp", "txt", "text"],
    "epub": ["html", "txt", "text", "md", "markdown"],
    "md": ["html"],
    "markdown": ["html"],
    "html": ["pdf"],
    "htm": ["pdf"],
    # ── Image conversions ─────────────────────────────────────────────
    "png": ["jpeg", "jpg", "bmp", "tiff", "webp", "gif", "pdf"],
    "jpeg": ["png", "bmp", "tiff", "webp", "gif", "pdf"],
    "jpg": ["png", "bmp", "tiff", "webp", "gif", "pdf"],
    "bmp": ["png", "jpeg", "jpg", "tiff", "webp", "gif", "pdf"],
    "tiff": ["png", "jpeg", "jpg", "bmp", "webp", "gif", "pdf"],
    "tif": ["png", "jpeg", "jpg", "bmp", "webp", "gif", "pdf"],
    "webp": ["png", "jpeg", "jpg", "bmp", "tiff", "gif", "pdf"],
    "gif": ["png", "jpeg", "jpg", "bmp", "tiff", "webp"],
    # ── Video conversions ─────────────────────────────────────────────
    "mp4": ["mkv", "avi", "webm", "mov", "gif", "mp3", "wav", "flac", "ogg", "aac"],
    "mkv": ["mp4", "avi", "webm", "mov", "gif", "mp3", "wav", "flac", "ogg", "aac"],
    "avi": ["mp4", "mkv", "webm", "mov", "gif", "mp3", "wav", "flac", "ogg", "aac"],
    "webm": ["mp4", "mkv", "avi", "mov", "gif", "mp3", "wav", "flac", "ogg", "aac"],
    "mov": ["mp4", "mkv", "avi", "webm", "gif", "mp3", "wav", "flac", "ogg", "aac"],
    # ── Audio conversions ─────────────────────────────────────────────
    "mp3": ["wav", "flac", "ogg", "aac", "m4a"],
    "wav": ["mp3", "flac", "ogg", "aac", "m4a"],
    "flac": ["mp3", "wav", "ogg", "aac", "m4a"],
    "ogg": ["mp3", "wav", "flac", "aac", "m4a"],
    "aac": ["mp3", "wav", "flac", "ogg", "m4a"],
    "m4a": ["mp3", "wav", "flac", "ogg", "aac"],
}

# Audio formats used to distinguish "extract audio" from "transcode video".
_AUDIO_EXTENSIONS = frozenset({
    "mp3", "wav", "flac", "ogg", "aac", "m4a", "wma", "opus",
})

# Video formats.
_VIDEO_EXTENSIONS = frozenset({
    "mp4", "mkv", "avi", "webm", "mov", "wmv", "flv", "ts", "m4v",
})

# Image formats.
_IMAGE_EXTENSIONS = frozenset({
    "png", "jpeg", "jpg", "bmp", "tiff", "tif", "webp", "gif",
})

# Document formats.
_DOCUMENT_EXTENSIONS = frozenset({
    "pdf", "epub", "md", "markdown", "html", "htm", "txt", "text",
})
