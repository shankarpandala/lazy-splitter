"""Audio-specific data models for the lazy-splitter audio module.

These dataclasses extend the core models with audio-specific attributes such
as time-based boundaries, codec metadata, and encoding options.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, Dict, Optional


@dataclasses.dataclass
class AudioSegment:
    """A single audio segment defined by start and end timestamps.

    Attributes
    ----------
    title:
        Human-readable name for this segment (e.g. a chapter title).
    start_time:
        Start position in seconds from the beginning of the source file.
    end_time:
        End position in seconds from the beginning of the source file.
        May be ``None`` when the segment extends to the end of the file.
    detection_method:
        Name of the strategy that produced this segment (e.g. ``"silence"``).
    confidence:
        A value in ``[0.0, 1.0]`` indicating how confident the detector is
        about this boundary.  ``1.0`` for deterministic methods such as
        embedded chapters or CUE sheets.
    metadata:
        Arbitrary extra information (performer, ISRC, etc.).
    """

    title: str
    start_time: float
    end_time: Optional[float] = None
    detection_method: str = "unknown"
    confidence: float = 1.0
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)

    # -- helpers -------------------------------------------------------------

    @property
    def duration(self) -> Optional[float]:
        """Duration of the segment in seconds, or ``None`` if open-ended."""
        if self.end_time is not None:
            return self.end_time - self.start_time
        return None

    def __repr__(self) -> str:
        end = f"{self.end_time:.3f}" if self.end_time is not None else "EOF"
        return (
            f"AudioSegment(title={self.title!r}, "
            f"start={self.start_time:.3f}, end={end}, "
            f"method={self.detection_method!r}, "
            f"confidence={self.confidence:.2f})"
        )


@dataclasses.dataclass
class AudioInfo:
    """Metadata about an audio file.

    Attributes
    ----------
    path:
        Absolute path to the file.
    duration:
        Total duration in seconds.
    codec:
        Audio codec name (e.g. ``"mp3"``, ``"aac"``, ``"flac"``).
    bitrate:
        Bit-rate in bits-per-second, or ``None`` if not applicable.
    sample_rate:
        Sample rate in Hz (e.g. ``44100``).
    channels:
        Number of audio channels (1 = mono, 2 = stereo).
    tags:
        ID3 / Vorbis / other tag data.
    file_size:
        Size of the file in bytes.
    format_name:
        Container format description (e.g. ``"MPEG audio"``, ``"FLAC"``).
    """

    path: Path
    duration: float
    codec: str = "unknown"
    bitrate: Optional[int] = None
    sample_rate: int = 44100
    channels: int = 2
    tags: Dict[str, Any] = dataclasses.field(default_factory=dict)
    file_size: int = 0
    format_name: str = "unknown"

    @property
    def duration_formatted(self) -> str:
        """Return duration as ``HH:MM:SS``."""
        total = int(self.duration)
        hours, remainder = divmod(total, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    @property
    def bitrate_kbps(self) -> Optional[float]:
        """Bit-rate in kbps, or ``None``."""
        if self.bitrate is not None:
            return self.bitrate / 1000.0
        return None


@dataclasses.dataclass
class AudioSplitOptions:
    """Options that control how audio segments are written to disk.

    Attributes
    ----------
    output_format:
        Target container/codec format (``"mp3"``, ``"flac"``, etc.).
    bitrate:
        Target bitrate string understood by *pydub* / *ffmpeg*
        (e.g. ``"192k"``, ``"320k"``).  Ignored for lossless formats.
    sample_rate:
        Target sample rate in Hz.  ``None`` keeps the source rate.
    channels:
        Target channel count.  ``None`` keeps the source layout.
    normalize:
        If ``True``, normalise audio to ``-0.1 dBFS`` before writing.
    fade_in_ms:
        Fade-in duration in milliseconds applied at the start of each segment.
    fade_out_ms:
        Fade-out duration in milliseconds applied at the end of each segment.
    """

    output_format: str = "mp3"
    bitrate: Optional[str] = "192k"
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    normalize: bool = False
    fade_in_ms: int = 0
    fade_out_ms: int = 0

    # -- validation ----------------------------------------------------------

    #: Formats the splitter knows how to write.
    SUPPORTED_FORMATS = frozenset({"mp3", "flac", "wav", "ogg", "aac", "m4a", "opus"})

    def __post_init__(self) -> None:
        self.output_format = self.output_format.lower().strip(".")
        if self.output_format not in self.SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported output format {self.output_format!r}. "
                f"Choose from: {', '.join(sorted(self.SUPPORTED_FORMATS))}"
            )
        if self.fade_in_ms < 0 or self.fade_out_ms < 0:
            raise ValueError("Fade durations must be non-negative.")
