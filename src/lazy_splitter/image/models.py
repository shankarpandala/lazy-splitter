"""Image-specific data models for the lazy-splitter image module.

These dataclasses describe individual image frames, overall image metadata,
and the options that control how an image is split.  They are intentionally
lightweight and rely only on the standard library so that they can be
imported even when Pillow is not installed.

The :class:`ImageFrame` defined here extends the core
:class:`~lazy_splitter.core.models.ImageFrame` with an optional *region*
field that describes a rectangular sub-area within the source image.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


@dataclasses.dataclass
class ImageFrame:
    """A single frame or region detected inside an image file.

    This is the image module's own frame descriptor.  It mirrors the fields
    of :class:`lazy_splitter.core.models.ImageFrame` and adds a *region*
    field so that grid-based and content-aware detectors can express
    sub-image bounding boxes.

    Attributes
    ----------
    title:
        Human-readable label for the frame (e.g. ``"Frame 3"``).
    index:
        Zero-based position of this frame in the source image.
    width:
        Width of the frame in pixels.
    height:
        Height of the frame in pixels.
    format:
        Image format string (e.g. ``"PNG"``, ``"TIFF"``).
    metadata:
        Arbitrary extra information attached by the detector.
    region:
        Optional bounding box expressed as ``(x, y, width, height)`` in
        pixels.  When *None* the frame spans the entire canvas.
    """

    title: str
    index: int
    width: int = 0
    height: int = 0
    format: str = ""
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)
    region: Optional[Tuple[int, int, int, int]] = None


@dataclasses.dataclass
class ImageInfo:
    """Summarised metadata for an image file on disk.

    Attributes
    ----------
    path:
        Filesystem path to the image.
    width:
        Width of the first frame in pixels.
    height:
        Height of the first frame in pixels.
    format:
        Image format as reported by Pillow (e.g. ``"TIFF"``, ``"GIF"``).
    mode:
        Pillow colour mode (e.g. ``"RGB"``, ``"RGBA"``, ``"L"``).
    frame_count:
        Number of frames / pages contained in the image.
    dpi:
        Dots-per-inch as a ``(x_dpi, y_dpi)`` tuple, or *None* when the
        image does not carry DPI metadata.
    has_exif:
        Whether the image contains EXIF metadata.
    file_size:
        Size of the image file in bytes.
    is_animated:
        Whether the image contains animation data (GIF, APNG, WebP).
    """

    path: Path
    width: int = 0
    height: int = 0
    format: str = ""
    mode: str = ""
    frame_count: int = 1
    dpi: Optional[Tuple[float, float]] = None
    has_exif: bool = False
    file_size: int = 0
    is_animated: bool = False


@dataclasses.dataclass
class ImageSplitOptions:
    """Options that control how an image is split and how outputs are written.

    Attributes
    ----------
    output_format:
        Target format for the split images.  Supported values include
        ``"png"``, ``"jpeg"``, ``"webp"``, ``"tiff"``, and ``"bmp"``.
        Defaults to ``"png"``.
    quality:
        Compression quality for lossy formats (1--100).  Only meaningful
        for JPEG and WebP.  Defaults to ``95``.
    dpi:
        Output resolution as a ``(x_dpi, y_dpi)`` tuple.  When *None*
        the original DPI is preserved (if available).
    color_space:
        Target colour mode (e.g. ``"RGB"``, ``"L"``, ``"CMYK"``).  When
        *None* the original mode is preserved.
    preserve_exif:
        Whether to copy EXIF metadata from the source to every output
        image.  Defaults to ``True``.
    generate_thumbnails:
        Whether to create a thumbnail alongside each full-size output.
        Defaults to ``False``.
    thumbnail_size:
        Maximum dimensions ``(width, height)`` for thumbnails.  Pillow's
        ``Image.thumbnail`` respects the aspect ratio.  Defaults to
        ``(256, 256)``.
    skip_blank:
        Whether to skip frames that are detected as blank (solid colour
        or near-solid).  Defaults to ``False``.
    """

    output_format: str = "png"
    quality: int = 95
    dpi: Optional[Tuple[float, float]] = None
    color_space: Optional[str] = None
    preserve_exif: bool = True
    generate_thumbnails: bool = False
    thumbnail_size: Tuple[int, int] = (256, 256)
    skip_blank: bool = False
