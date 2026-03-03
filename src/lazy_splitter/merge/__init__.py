"""Merge / join module for lazy-splitter.

This package provides merger classes that reassemble previously-split files
(or arbitrary collections of files) back into a single output.  Each merger
targets a specific media family and relies on the same optional-import
pattern used throughout lazy-splitter so that heavy dependencies are only
required when a particular merger is actually used.

Exported classes
----------------
* :class:`PDFMerger`       -- combine PDF files (PyMuPDF / fitz).
* :class:`EpubMerger`      -- combine EPUB e-books (ebooklib).
* :class:`VideoMerger`     -- concatenate video files (FFmpeg).
* :class:`AudioMerger`     -- concatenate audio files (pydub).
* :class:`DocumentMerger`  -- merge DOCX, PPTX, Markdown, and CSV files.
"""

from __future__ import annotations

from lazy_splitter.merge.audio_merger import AudioMerger
from lazy_splitter.merge.document_merger import DocumentMerger
from lazy_splitter.merge.epub_merger import EpubMerger
from lazy_splitter.merge.pdf_merger import PDFMerger
from lazy_splitter.merge.video_merger import VideoMerger

__all__ = [
    "AudioMerger",
    "DocumentMerger",
    "EpubMerger",
    "PDFMerger",
    "VideoMerger",
]
