"""Format conversion module for lazy-splitter.

This package provides converters for transforming files between document,
media, and image formats.  The main entry-point is :class:`FormatConverter`,
which auto-dispatches to specialised back-ends depending on the input and
output format.

Quick-start::

    from lazy_splitter.convert import FormatConverter

    converter = FormatConverter()
    result = converter.convert(Path("input.pdf"), Path("output.txt"), "txt")

For lower-level access, use the specialised converters directly::

    from lazy_splitter.convert import DocumentConverter, MediaConverter
"""

from __future__ import annotations

from lazy_splitter.convert.converter import FormatConverter
from lazy_splitter.convert.document_converter import DocumentConverter
from lazy_splitter.convert.media_converter import MediaConverter
from lazy_splitter.convert.models import CONVERSION_MAP, ConversionOptions

__all__ = [
    "FormatConverter",
    "DocumentConverter",
    "MediaConverter",
    "ConversionOptions",
    "CONVERSION_MAP",
]
