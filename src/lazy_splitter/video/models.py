"""Video-specific data models for the lazy-splitter video module.

This module defines the dataclasses used to represent video segments, video
file metadata, and splitting options.  They extend the generic core models
with fields that are meaningful only in a video context (codecs, resolution,
keyframe alignment, etc.).
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclasses.dataclass
class VideoSegment:
    """A single detected segment within a video file.

    Attributes
    ----------
    title:
        Human-readable title for the segment (e.g. chapter name).
    start_time:
        Start position in seconds from the beginning of the file.
    end_time:
        End position in seconds from the beginning of the file.
    detection_method:
        The strategy that produced this segment (``"chapters"``,
        ``"scenes"``, ``"silence"``, ``"timestamps"``, ``"hybrid"``).
    confidence:
        Confidence score between 0.0 and 1.0 indicating how reliable
        the boundary detection is.  ``1.0`` for user-provided or
        embedded chapter data.
    thumbnail_path:
        Optional path to a generated thumbnail image for the segment.
    metadata:
        Arbitrary extra information (scene score, silence duration, etc.).
    """

    title: str
    start_time: float
    end_time: float
    detection_method: str = "unknown"
    confidence: float = 1.0
    thumbnail_path: Optional[Path] = None
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)

    @property
    def duration(self) -> float:
        """Duration of this segment in seconds."""
        return self.end_time - self.start_time

    def __post_init__(self) -> None:
        if self.start_time < 0:
            raise ValueError("start_time must be non-negative")
        if self.end_time < self.start_time:
            raise ValueError("end_time must be >= start_time")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")


@dataclasses.dataclass
class VideoInfo:
    """Metadata about a video file obtained via ffprobe.

    Attributes
    ----------
    path:
        Absolute path to the video file.
    duration:
        Total duration in seconds.
    width:
        Video frame width in pixels.
    height:
        Video frame height in pixels.
    codec:
        Video codec name (e.g. ``"h264"``, ``"hevc"``, ``"vp9"``).
    bitrate:
        Overall bitrate in bits per second.
    fps:
        Frames per second (as a float to accommodate fractional values
        like 23.976).
    audio_codec:
        Audio codec name (e.g. ``"aac"``, ``"opus"``), or ``None`` if
        no audio stream is present.
    chapters_count:
        Number of embedded chapter markers.
    format_name:
        Container format name (e.g. ``"matroska,webm"``, ``"mov,mp4"``).
    file_size:
        File size in bytes.
    """

    path: Path
    duration: float
    width: int
    height: int
    codec: str
    bitrate: int
    fps: float
    audio_codec: Optional[str] = None
    chapters_count: int = 0
    format_name: str = ""
    file_size: int = 0

    @property
    def resolution(self) -> Tuple[int, int]:
        """Return ``(width, height)`` tuple."""
        return (self.width, self.height)

    @property
    def aspect_ratio(self) -> float:
        """Return the aspect ratio as a float (width / height)."""
        if self.height == 0:
            return 0.0
        return self.width / self.height


@dataclasses.dataclass
class VideoSplitOptions:
    """Configuration options for a video split operation.

    Attributes
    ----------
    codec:
        Output video codec.  Use ``"copy"`` for lossless stream copy
        (no re-encoding), or one of ``"h264"``, ``"h265"``, ``"vp9"``,
        ``"av1"`` for re-encoding.
    quality_preset:
        Encoder speed/quality trade-off preset.  Typical values are
        ``"ultrafast"``, ``"fast"``, ``"medium"``, ``"slow"``,
        ``"veryslow"``.  Only relevant when *codec* is not ``"copy"``.
    resolution:
        Target resolution as an ``(width, height)`` tuple, or ``None``
        to keep the original resolution.  Set either dimension to
        ``-1`` to auto-scale while preserving the aspect ratio.
    audio_codec:
        Output audio codec.  Use ``"copy"`` to pass through without
        re-encoding, or specify a codec name (e.g. ``"aac"``,
        ``"opus"``).
    subtitle_handling:
        How to handle subtitles: ``"copy"`` to include them,
        ``"burn"`` to hard-sub them into the video, or ``"drop"``
        to exclude them.
    keyframe_align:
        When ``True`` (the default), adjust split points to the nearest
        preceding keyframe so that stream-copy splits start on a clean
        I-frame boundary.
    """

    codec: str = "copy"
    quality_preset: str = "medium"
    resolution: Optional[Tuple[int, int]] = None
    audio_codec: str = "copy"
    subtitle_handling: str = "copy"
    keyframe_align: bool = True

    # Valid values -----------------------------------------------------------
    VALID_CODECS: Tuple[str, ...] = (
        "copy", "h264", "h265", "vp9", "av1",
    )
    VALID_QUALITY_PRESETS: Tuple[str, ...] = (
        "ultrafast", "superfast", "veryfast", "faster", "fast",
        "medium", "slow", "slower", "veryslow",
    )
    VALID_SUBTITLE_HANDLING: Tuple[str, ...] = ("copy", "burn", "drop")

    def __post_init__(self) -> None:
        if self.codec not in self.VALID_CODECS:
            raise ValueError(
                f"Invalid codec {self.codec!r}; "
                f"choose from {self.VALID_CODECS}"
            )
        if self.quality_preset not in self.VALID_QUALITY_PRESETS:
            raise ValueError(
                f"Invalid quality_preset {self.quality_preset!r}; "
                f"choose from {self.VALID_QUALITY_PRESETS}"
            )
        if self.subtitle_handling not in self.VALID_SUBTITLE_HANDLING:
            raise ValueError(
                f"Invalid subtitle_handling {self.subtitle_handling!r}; "
                f"choose from {self.VALID_SUBTITLE_HANDLING}"
            )

    @property
    def needs_reencode(self) -> bool:
        """Return ``True`` if the options require re-encoding."""
        return self.codec != "copy" or self.resolution is not None

    def to_ffmpeg_args(self) -> List[str]:
        """Build a list of FFmpeg output arguments from these options.

        Returns
        -------
        list of str
            Arguments suitable for passing to an ``ffmpeg`` subprocess
            invocation (e.g. ``["-c:v", "libx264", "-preset", "medium"]``).
        """
        args: List[str] = []

        # -- Video codec -----------------------------------------------------
        codec_map = {
            "copy": "copy",
            "h264": "libx264",
            "h265": "libx265",
            "vp9": "libvpx-vp9",
            "av1": "libaom-av1",
        }
        args.extend(["-c:v", codec_map[self.codec]])

        if self.codec != "copy":
            args.extend(["-preset", self.quality_preset])

        # -- Resolution scaling ----------------------------------------------
        if self.resolution is not None:
            w, h = self.resolution
            args.extend(["-vf", f"scale={w}:{h}"])

        # -- Audio codec -----------------------------------------------------
        args.extend(["-c:a", self.audio_codec])

        # -- Subtitles -------------------------------------------------------
        if self.subtitle_handling == "copy":
            args.extend(["-c:s", "copy"])
        elif self.subtitle_handling == "drop":
            args.append("-sn")
        # "burn" is handled separately via a video filter in the splitter

        return args
