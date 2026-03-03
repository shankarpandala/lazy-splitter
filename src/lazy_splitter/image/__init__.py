"""Image splitting module for lazy-splitter.

This package provides detection and splitting capabilities for image files
including multi-page TIFFs, animated GIFs / WebP / APNG, grid-based
partitioning, content-aware region detection, and sprite-sheet extraction.

Pillow (``PIL``) is required at runtime but is imported lazily so that
this package can be imported for introspection even when Pillow is absent.

Quick start::

    from lazy_splitter.image import ImageDetector, ImageSplitter

    detector = ImageDetector()
    result = detector.detect("scan.tiff", strategy="auto")

    splitter = ImageSplitter()
    split_result = splitter.split("scan.tiff", result.segments)
"""

from __future__ import annotations

from lazy_splitter.image.detector import ImageDetector
from lazy_splitter.image.models import ImageFrame, ImageInfo, ImageSplitOptions
from lazy_splitter.image.splitter import ImageSplitter

__all__ = [
    "ImageDetector",
    "ImageFrame",
    "ImageInfo",
    "ImageSplitOptions",
    "ImageSplitter",
]
