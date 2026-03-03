"""CUE sheet parser for audio chapter detection.

CUE sheets (``.cue`` files) are plain-text metadata files that describe the
track layout of a CD or a single audio file.  This module parses the subset
of CUE directives that are relevant for splitting: ``FILE``, ``TRACK``,
``INDEX``, ``TITLE``, and ``PERFORMER``.

References
----------
* https://en.wikipedia.org/wiki/Cue_sheet_(computing)
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lazy_splitter.audio.models import AudioSegment

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

def _cue_timestamp_to_seconds(mm: int, ss: int, ff: int) -> float:
    """Convert a CUE ``MM:SS:FF`` timestamp to seconds.

    In the CUE specification, *FF* are **frames** where 1 second = 75 frames.

    Parameters
    ----------
    mm:
        Minutes component.
    ss:
        Seconds component.
    ff:
        Frames component (0-74).

    Returns
    -------
    float
        The timestamp in fractional seconds.
    """
    return mm * 60.0 + ss + ff / 75.0


_TIMESTAMP_RE = re.compile(r"(\d+):(\d+):(\d+)")


def _parse_timestamp(raw: str) -> float:
    """Parse a CUE timestamp string (``MM:SS:FF``) into seconds.

    Parameters
    ----------
    raw:
        A string of the form ``"MM:SS:FF"``.

    Returns
    -------
    float
        Seconds.

    Raises
    ------
    ValueError
        If *raw* does not match the expected format.
    """
    match = _TIMESTAMP_RE.match(raw.strip())
    if not match:
        raise ValueError(f"Invalid CUE timestamp: {raw!r}")
    mm, ss, ff = int(match.group(1)), int(match.group(2)), int(match.group(3))
    return _cue_timestamp_to_seconds(mm, ss, ff)


# ---------------------------------------------------------------------------
# Internal track accumulator
# ---------------------------------------------------------------------------

class _TrackInfo:
    """Mutable accumulator used while parsing a single ``TRACK`` block."""

    __slots__ = ("number", "title", "performer", "index00", "index01", "extras")

    def __init__(self, number: int) -> None:
        self.number: int = number
        self.title: Optional[str] = None
        self.performer: Optional[str] = None
        self.index00: Optional[float] = None  # pre-gap
        self.index01: Optional[float] = None  # actual start
        self.extras: Dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_cue(cue_path: str) -> List[AudioSegment]:
    """Parse a CUE sheet and return a list of :class:`AudioSegment` objects.

    The parser handles the following directives:

    * ``FILE`` -- recorded but not used for splitting decisions.
    * ``PERFORMER`` -- at the disc or track level.
    * ``TITLE`` -- at the disc or track level.
    * ``TRACK`` -- starts a new track block.
    * ``INDEX 00`` / ``INDEX 01`` -- pre-gap and start positions.

    Parameters
    ----------
    cue_path:
        Path to the ``.cue`` file.  May be a string or :class:`~pathlib.Path`.

    Returns
    -------
    list[AudioSegment]
        One segment per track, ordered by start time.  The last segment has
        ``end_time=None`` because the CUE sheet does not encode the total
        duration of the audio file.

    Raises
    ------
    FileNotFoundError
        If *cue_path* does not exist.
    ValueError
        If the CUE sheet contains no parseable tracks.
    """
    path = Path(cue_path)
    if not path.is_file():
        raise FileNotFoundError(f"CUE file not found: {path}")

    # Try several common encodings
    text: Optional[str] = None
    for encoding in ("utf-8-sig", "utf-8", "latin-1", "shift_jis"):
        try:
            text = path.read_text(encoding=encoding)
            break
        except (UnicodeDecodeError, LookupError):
            continue

    if text is None:
        # Last-resort: read as latin-1 which never raises
        text = path.read_text(encoding="latin-1")

    return _parse_cue_text(text)


def _parse_cue_text(text: str) -> List[AudioSegment]:
    """Parse the textual content of a CUE sheet.

    This is the inner workhorse; :func:`parse_cue` handles file I/O and
    encoding detection before delegating here.
    """
    tracks: List[_TrackInfo] = []
    current_track: Optional[_TrackInfo] = None

    disc_title: Optional[str] = None
    disc_performer: Optional[str] = None
    referenced_file: Optional[str] = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        upper = line.upper()

        # -- FILE directive --------------------------------------------------
        if upper.startswith("FILE "):
            referenced_file = _unquote(line[5:].rsplit(" ", 1)[0])
            continue

        # -- disc-level PERFORMER / TITLE ------------------------------------
        if upper.startswith("PERFORMER ") and current_track is None:
            disc_performer = _unquote(line[10:])
            continue

        if upper.startswith("TITLE ") and current_track is None:
            disc_title = _unquote(line[6:])
            continue

        # -- TRACK -----------------------------------------------------------
        if upper.startswith("TRACK "):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    track_num = int(parts[1])
                except ValueError:
                    logger.warning("Skipping TRACK line with non-integer number: %s", line)
                    continue
                current_track = _TrackInfo(track_num)
                tracks.append(current_track)
            continue

        # Inside a TRACK block -----------------------------------------------
        if current_track is None:
            continue

        if upper.startswith("TITLE "):
            current_track.title = _unquote(line[6:])
        elif upper.startswith("PERFORMER "):
            current_track.performer = _unquote(line[10:])
        elif upper.startswith("INDEX "):
            parts = line.split()
            if len(parts) >= 3:
                index_num = parts[1]
                timestamp_raw = parts[2]
                try:
                    ts = _parse_timestamp(timestamp_raw)
                except ValueError:
                    logger.warning("Skipping malformed INDEX timestamp: %s", line)
                    continue
                if index_num == "00":
                    current_track.index00 = ts
                elif index_num == "01":
                    current_track.index01 = ts
                # Higher indices are rare; we ignore them for splitting purposes.
        elif upper.startswith("ISRC "):
            current_track.extras["isrc"] = line.split(None, 1)[1].strip()
        elif upper.startswith("REM "):
            # Preserve remark fields
            rem_content = line[4:].strip()
            if " " in rem_content:
                key, value = rem_content.split(" ", 1)
                current_track.extras[f"rem_{key.lower()}"] = value.strip('"').strip()

    if not tracks:
        raise ValueError("CUE sheet contains no parseable tracks.")

    # -- Convert _TrackInfo list into AudioSegment list ----------------------
    segments: List[AudioSegment] = []
    for i, track in enumerate(tracks):
        start = track.index01 if track.index01 is not None else (track.index00 or 0.0)

        # Determine end time from the next track's start
        end_time: Optional[float] = None
        if i + 1 < len(tracks):
            next_track = tracks[i + 1]
            # Prefer INDEX 00 (pre-gap) of next track as boundary; fall back
            # to INDEX 01.
            if next_track.index00 is not None:
                end_time = next_track.index00
            elif next_track.index01 is not None:
                end_time = next_track.index01

        title = track.title or f"Track {track.number:02d}"

        metadata: Dict[str, Any] = {}
        if track.performer:
            metadata["performer"] = track.performer
        elif disc_performer:
            metadata["performer"] = disc_performer
        if disc_title:
            metadata["album"] = disc_title
        if referenced_file:
            metadata["file"] = referenced_file
        metadata["track_number"] = track.number
        metadata.update(track.extras)

        segments.append(
            AudioSegment(
                title=title,
                start_time=start,
                end_time=end_time,
                detection_method="cue",
                confidence=1.0,
                metadata=metadata,
            )
        )

    return segments


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _unquote(value: str) -> str:
    """Strip surrounding double-quotes and whitespace from *value*."""
    value = value.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value
