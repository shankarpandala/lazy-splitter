"""Audio splitting and chapter detection for lazy-splitter.

This package provides tools for detecting chapters or logical segments in
audio files and splitting them into individual files with proper tagging.

Supported detection strategies:

* **silence** -- locate gaps of silence via *pydub*.
* **chapters** -- read embedded chapter marks (M4B, MP3 CHAP frames).
* **cue** -- parse an external CUE sheet.
* **duration** -- split into fixed-length segments.
* **bpm** -- detect tempo with *librosa* and split at bar boundaries.
* **hybrid** -- try chapters, then CUE, then silence.

Supported output formats: MP3, FLAC, WAV, OGG, AAC, M4A, Opus.

Example
-------
>>> from lazy_splitter.audio import AudioChapterDetector, AudioSplitter
>>> detector = AudioChapterDetector()
>>> result = detector.detect("audiobook.m4b", strategy="chapters")
>>> splitter = AudioSplitter()
>>> split = splitter.split("audiobook.m4b", result.segments, output_format="mp3")
"""

from lazy_splitter.audio.cue_parser import parse_cue
from lazy_splitter.audio.detector import AudioChapterDetector
from lazy_splitter.audio.models import AudioInfo, AudioSegment, AudioSplitOptions
from lazy_splitter.audio.splitter import AudioSplitter

__all__ = [
    "AudioChapterDetector",
    "AudioInfo",
    "AudioSegment",
    "AudioSplitOptions",
    "AudioSplitter",
    "parse_cue",
]
