"""Video splitting and chapter detection for lazy-splitter.

This package provides tools to detect segment boundaries in video files
(using embedded chapters, scene detection, silence analysis, or
user-supplied timestamps) and to split them into individual files using
FFmpeg.

Quick start
-----------
::

    from lazy_splitter.video import VideoChapterDetector, VideoSplitter

    detector = VideoChapterDetector()
    result = detector.detect("movie.mkv", strategy="chapters")

    splitter = VideoSplitter()
    split_result = splitter.split("movie.mkv", result.segments)

Classes
-------
VideoChapterDetector
    Detects chapter / segment boundaries in video files.
VideoSplitter
    Splits video files into segments using FFmpeg.
VideoSegment
    Dataclass representing a single video segment.
VideoInfo
    Dataclass holding video file metadata.
VideoSplitOptions
    Dataclass for configuring split codec, quality, and resolution.
"""

from __future__ import annotations

from lazy_splitter.video.detector import VideoChapterDetector
from lazy_splitter.video.models import VideoInfo, VideoSegment, VideoSplitOptions
from lazy_splitter.video.splitter import VideoSplitter

__all__ = [
    "VideoChapterDetector",
    "VideoInfo",
    "VideoSegment",
    "VideoSplitOptions",
    "VideoSplitter",
]
