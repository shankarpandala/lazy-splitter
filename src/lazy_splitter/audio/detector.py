"""Audio chapter / segment detection.

:class:`AudioChapterDetector` implements six detection strategies:

* **silence** -- detect gaps of silence using *pydub*.
* **chapters** -- read embedded chapter marks from M4B / MP3 files via *mutagen*.
* **cue** -- parse an external CUE sheet.
* **duration** -- split into fixed-length segments.
* **bpm** -- detect tempo with *librosa* and split at bar boundaries.
* **hybrid** -- try *chapters* first, then fall back to *silence*.

All three optional dependencies (*pydub*, *mutagen*, *librosa*) are imported
lazily so that the module can be loaded even when they are not installed.
"""

from __future__ import annotations

import json
import logging
import math
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from lazy_splitter.audio.models import AudioInfo, AudioSegment
from lazy_splitter.core.base import BaseDetector
from lazy_splitter.core.exceptions import DetectionError
from lazy_splitter.core.models import DetectionResult

# ---------------------------------------------------------------------------
# Optional dependency imports
# ---------------------------------------------------------------------------

try:
    from pydub import AudioSegment as PydubSegment  # type: ignore[import-untyped]
    from pydub.silence import detect_silence as pydub_detect_silence  # type: ignore[import-untyped]

    _HAS_PYDUB = True
except ImportError:  # pragma: no cover
    _HAS_PYDUB = False

try:
    import mutagen  # type: ignore[import-untyped]
    from mutagen.mp3 import MP3  # type: ignore[import-untyped]
    from mutagen.mp4 import MP4  # type: ignore[import-untyped]

    _HAS_MUTAGEN = True
except ImportError:  # pragma: no cover
    _HAS_MUTAGEN = False

try:
    import librosa  # type: ignore[import-untyped]
    import numpy as np  # type: ignore[import-untyped]

    _HAS_LIBROSA = True
except ImportError:  # pragma: no cover
    _HAS_LIBROSA = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Strategy registry
# ---------------------------------------------------------------------------

_VALID_STRATEGIES = frozenset({
    "silence",
    "chapters",
    "cue",
    "duration",
    "bpm",
    "hybrid",
})


# ---------------------------------------------------------------------------
# AudioChapterDetector
# ---------------------------------------------------------------------------

class AudioChapterDetector(BaseDetector):
    """Detect chapters or logical segments in an audio file.

    Parameters
    ----------
    logger:
        Optional logger instance.  Defaults to the module-level logger.
    """

    def detect(
        self,
        input_path: Path,
        strategy: str = "hybrid",
        **kwargs: Any,
    ) -> DetectionResult:
        """Run the requested detection strategy on *input_path*.

        Parameters
        ----------
        input_path:
            Path to the audio file.
        strategy:
            One of ``"silence"``, ``"chapters"``, ``"cue"``, ``"duration"``,
            ``"bpm"``, or ``"hybrid"``.
        **kwargs:
            Strategy-specific options forwarded to the private ``_detect_*``
            methods.

        Returns
        -------
        DetectionResult
            Detected segments and metadata.

        Raises
        ------
        DetectionError
            If the strategy name is unknown, required dependencies are missing,
            or detection fails.
        """
        path = Path(input_path)
        if not path.is_file():
            raise DetectionError(f"Audio file not found: {path}", path=str(path))

        strategy = strategy.lower()
        if strategy not in _VALID_STRATEGIES:
            raise DetectionError(
                f"Unknown detection strategy {strategy!r}. "
                f"Choose from: {', '.join(sorted(_VALID_STRATEGIES))}",
                strategy=strategy,
            )

        self.logger.info("Detecting segments in %s using strategy=%r", path.name, strategy)

        dispatch = {
            "silence": self._detect_from_silence,
            "chapters": self._detect_from_chapters,
            "cue": self._detect_from_cue,
            "duration": self._detect_from_duration,
            "bpm": self._detect_from_bpm,
            "hybrid": self._detect_hybrid,
        }

        try:
            segments = dispatch[strategy](path, **kwargs)
        except DetectionError:
            raise
        except Exception as exc:
            raise DetectionError(
                f"Detection failed ({strategy}): {exc}",
                strategy=strategy,
                path=str(path),
            ) from exc

        self.logger.info("Detected %d segment(s) via %s", len(segments), strategy)

        return DetectionResult(
            chapters=segments,
            strategy_used=strategy,
            total_items=len(segments),
            source_path=str(path),
            metadata={"detector": self.__class__.__name__},
            file_type=path.suffix.lstrip(".").lower(),
        )

    # ------------------------------------------------------------------
    # Strategy: silence
    # ------------------------------------------------------------------

    def _detect_from_silence(
        self,
        path: Path,
        min_silence_len: int = 1000,
        silence_thresh: int = -40,
        **kwargs: Any,
    ) -> List[AudioSegment]:
        """Detect chapters by locating silence gaps.

        Parameters
        ----------
        path:
            Path to the audio file.
        min_silence_len:
            Minimum length of silence (ms) to be considered a break.
        silence_thresh:
            Silence threshold in dBFS.

        Returns
        -------
        list[AudioSegment]
        """
        if not _HAS_PYDUB:
            raise DetectionError(
                "The 'pydub' package is required for silence detection. "
                "Install it with: pip install pydub"
            )

        self.logger.debug(
            "Loading audio for silence detection (min_len=%d ms, thresh=%d dBFS)",
            min_silence_len,
            silence_thresh,
        )

        audio = PydubSegment.from_file(str(path))
        total_duration_s = len(audio) / 1000.0

        # pydub returns list of [start_ms, end_ms] for each silent region
        silent_ranges = pydub_detect_silence(
            audio,
            min_silence_len=min_silence_len,
            silence_thresh=silence_thresh,
        )

        if not silent_ranges:
            # No silence found -- treat the whole file as one segment
            return [
                AudioSegment(
                    title="Full Track",
                    start_time=0.0,
                    end_time=total_duration_s,
                    detection_method="silence",
                    confidence=0.5,
                )
            ]

        segments: List[AudioSegment] = []
        prev_end_ms = 0

        for idx, (sil_start_ms, sil_end_ms) in enumerate(silent_ranges, start=1):
            # The segment runs from the end of the previous silence to the
            # start of this silence.
            seg_start = prev_end_ms / 1000.0
            seg_end = sil_start_ms / 1000.0

            if seg_end - seg_start > 0.1:  # skip tiny artefacts
                segments.append(
                    AudioSegment(
                        title=f"Segment {len(segments) + 1:03d}",
                        start_time=seg_start,
                        end_time=seg_end,
                        detection_method="silence",
                        confidence=0.8,
                        metadata={
                            "silence_before_ms": sil_end_ms - sil_start_ms,
                        },
                    )
                )

            prev_end_ms = sil_end_ms

        # Trailing segment after the last silence
        if prev_end_ms / 1000.0 < total_duration_s - 0.1:
            segments.append(
                AudioSegment(
                    title=f"Segment {len(segments) + 1:03d}",
                    start_time=prev_end_ms / 1000.0,
                    end_time=total_duration_s,
                    detection_method="silence",
                    confidence=0.8,
                )
            )

        return segments

    # ------------------------------------------------------------------
    # Strategy: chapters (embedded metadata)
    # ------------------------------------------------------------------

    def _detect_from_chapters(
        self,
        path: Path,
        **kwargs: Any,
    ) -> List[AudioSegment]:
        """Read embedded chapter marks from M4B / MP4 / MP3 files.

        For M4B/MP4 files, chapters are stored in the ``chpl`` or Nero-style
        chapter atoms.  For MP3, the ``CHAP`` ID3 frame is used.  When
        *mutagen* cannot surface chapters directly we fall back to *ffprobe*.

        Parameters
        ----------
        path:
            Path to the audio file.

        Returns
        -------
        list[AudioSegment]
        """
        if not _HAS_MUTAGEN:
            raise DetectionError(
                "The 'mutagen' package is required for chapter detection. "
                "Install it with: pip install mutagen"
            )

        suffix = path.suffix.lower()
        segments: List[AudioSegment] = []

        # -- Try mutagen first -----------------------------------------------
        if suffix in (".m4b", ".m4a", ".mp4", ".aac"):
            segments = self._chapters_from_mp4(path)
        elif suffix in (".mp3",):
            segments = self._chapters_from_mp3(path)

        # -- Fallback: use ffprobe for any container -------------------------
        if not segments:
            segments = self._chapters_from_ffprobe(path)

        if not segments:
            raise DetectionError(
                f"No embedded chapters found in {path.name}",
                path=str(path),
            )

        return segments

    def _chapters_from_mp4(self, path: Path) -> List[AudioSegment]:
        """Extract chapters from an MP4/M4B file using mutagen."""
        segments: List[AudioSegment] = []
        try:
            mp4 = MP4(str(path))
        except Exception as exc:
            self.logger.warning("mutagen failed to open MP4: %s", exc)
            return segments

        # mutagen does not directly expose chapters for MP4 in a uniform way.
        # We check the common ``\xa9nam`` (title) and chapter-related atoms.
        # The most reliable path is the Nero chapter atom or the chpl box,
        # which mutagen exposes through mp4.tags if present, but the canonical
        # approach for M4B chapters is to use ffprobe.  We try tags first.
        if mp4.tags:
            # Look for chapter data in freeform atoms
            for key in mp4.tags:
                if "chap" in key.lower():
                    self.logger.debug("Found chapter-related atom: %s", key)

        # Duration for reference
        duration = mp4.info.length if mp4.info else 0.0
        if duration and not segments:
            self.logger.debug("MP4 duration=%.1fs, no direct chapter atoms found", duration)

        return segments

    def _chapters_from_mp3(self, path: Path) -> List[AudioSegment]:
        """Extract CHAP frames from an MP3 file using mutagen."""
        segments: List[AudioSegment] = []
        try:
            mp3 = MP3(str(path))
        except Exception as exc:
            self.logger.warning("mutagen failed to open MP3: %s", exc)
            return segments

        if mp3.tags is None:
            return segments

        # Collect CHAP frames
        chap_frames = []
        for key, frame in mp3.tags.items():
            if key.startswith("CHAP:"):
                chap_frames.append(frame)

        # Sort by start time
        chap_frames.sort(key=lambda f: getattr(f, "start_time", 0))

        for idx, frame in enumerate(chap_frames):
            start_ms = getattr(frame, "start_time", 0)
            end_ms = getattr(frame, "end_time", 0)

            # Extract title from sub-frames
            title = f"Chapter {idx + 1:02d}"
            sub_frames = getattr(frame, "sub_frames", None)
            if sub_frames:
                for sub_key in sub_frames:
                    sub = sub_frames[sub_key]
                    if hasattr(sub, "text") and sub.text:
                        title = str(sub.text[0])
                        break

            segments.append(
                AudioSegment(
                    title=title,
                    start_time=start_ms / 1000.0,
                    end_time=end_ms / 1000.0 if end_ms else None,
                    detection_method="chapters",
                    confidence=1.0,
                    metadata={"source": "id3_chap", "frame_id": getattr(frame, "element_id", "")},
                )
            )

        return segments

    @staticmethod
    def _chapters_from_ffprobe(path: Path) -> List[AudioSegment]:
        """Use *ffprobe* (if available) to extract chapter metadata."""
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v", "quiet",
                    "-print_format", "json",
                    "-show_chapters",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError:
            logger.debug("ffprobe not found on PATH; skipping chapter probe")
            return []
        except subprocess.TimeoutExpired:
            logger.warning("ffprobe timed out for %s", path.name)
            return []

        if result.returncode != 0:
            return []

        try:
            data = json.loads(result.stdout)
        except (json.JSONDecodeError, ValueError):
            return []

        chapters_raw = data.get("chapters", [])
        segments: List[AudioSegment] = []
        for idx, ch in enumerate(chapters_raw):
            start = float(ch.get("start_time", 0))
            end = float(ch.get("end_time", 0))
            tags = ch.get("tags", {})
            title = tags.get("title", f"Chapter {idx + 1:02d}")
            segments.append(
                AudioSegment(
                    title=title,
                    start_time=start,
                    end_time=end if end > start else None,
                    detection_method="chapters",
                    confidence=1.0,
                    metadata={"source": "ffprobe", **tags},
                )
            )

        return segments

    # ------------------------------------------------------------------
    # Strategy: CUE sheet
    # ------------------------------------------------------------------

    def _detect_from_cue(
        self,
        path: Path,
        cue_path: Optional[str] = None,
        **kwargs: Any,
    ) -> List[AudioSegment]:
        """Parse a CUE sheet and return the track boundaries.

        Parameters
        ----------
        path:
            Path to the audio file (used to auto-discover ``.cue`` siblings).
        cue_path:
            Explicit path to the CUE file.  If ``None`` the detector looks for
            a ``.cue`` file with the same stem next to *path*.

        Returns
        -------
        list[AudioSegment]
        """
        from lazy_splitter.audio.cue_parser import parse_cue

        if cue_path is None:
            candidate = path.with_suffix(".cue")
            if not candidate.is_file():
                raise DetectionError(
                    f"No CUE file specified and no sibling .cue found for {path.name}",
                    path=str(path),
                )
            cue_path = str(candidate)

        cue_file = Path(cue_path)
        if not cue_file.is_file():
            raise DetectionError(
                f"CUE file not found: {cue_file}",
                path=str(path),
                cue_path=str(cue_file),
            )

        self.logger.info("Parsing CUE sheet: %s", cue_file.name)
        return parse_cue(str(cue_file))

    # ------------------------------------------------------------------
    # Strategy: fixed duration
    # ------------------------------------------------------------------

    def _detect_from_duration(
        self,
        path: Path,
        segment_duration: float = 300.0,
        **kwargs: Any,
    ) -> List[AudioSegment]:
        """Split by fixed time intervals.

        Parameters
        ----------
        path:
            Path to the audio file.
        segment_duration:
            Length of each segment in seconds (default: 300 = 5 minutes).

        Returns
        -------
        list[AudioSegment]
        """
        if segment_duration <= 0:
            raise DetectionError("segment_duration must be positive", segment_duration=segment_duration)

        info = self.get_audio_info(path)
        total = info.duration
        if total <= 0:
            raise DetectionError("Cannot determine audio duration", path=str(path))

        num_segments = math.ceil(total / segment_duration)
        segments: List[AudioSegment] = []
        for i in range(num_segments):
            start = i * segment_duration
            end = min((i + 1) * segment_duration, total)
            segments.append(
                AudioSegment(
                    title=f"Part {i + 1:03d}",
                    start_time=start,
                    end_time=end,
                    detection_method="duration",
                    confidence=1.0,
                    metadata={"segment_duration": segment_duration},
                )
            )

        return segments

    # ------------------------------------------------------------------
    # Strategy: BPM / beat-based
    # ------------------------------------------------------------------

    def _detect_from_bpm(
        self,
        path: Path,
        bars_per_segment: int = 16,
        **kwargs: Any,
    ) -> List[AudioSegment]:
        """Detect tempo and split at bar boundaries.

        Parameters
        ----------
        path:
            Path to the audio file.
        bars_per_segment:
            Number of bars (measures) per output segment.  Assumes 4/4 time.

        Returns
        -------
        list[AudioSegment]
        """
        if not _HAS_LIBROSA:
            raise DetectionError(
                "The 'librosa' package is required for BPM detection. "
                "Install it with: pip install librosa"
            )

        self.logger.debug("Loading audio with librosa for BPM analysis...")
        y, sr = librosa.load(str(path), sr=None, mono=True)
        total_duration = float(len(y)) / sr

        # Estimate tempo
        tempo_array, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        # librosa >= 0.10 returns an array; older versions return a scalar
        if hasattr(tempo_array, "__len__") and len(tempo_array) > 0:
            bpm = float(tempo_array[0])
        else:
            bpm = float(tempo_array)

        if bpm <= 0:
            raise DetectionError("Could not determine BPM", path=str(path))

        self.logger.info("Estimated BPM: %.1f", bpm)

        # Convert beat frames to times
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)

        # Assuming 4/4 time: 1 bar = 4 beats
        beats_per_segment = bars_per_segment * 4
        segments: List[AudioSegment] = []
        seg_idx = 0

        for i in range(0, len(beat_times), beats_per_segment):
            start = float(beat_times[i])
            if i + beats_per_segment < len(beat_times):
                end = float(beat_times[i + beats_per_segment])
            else:
                end = total_duration

            segments.append(
                AudioSegment(
                    title=f"Section {seg_idx + 1:03d}",
                    start_time=start,
                    end_time=end,
                    detection_method="bpm",
                    confidence=0.7,
                    metadata={
                        "bpm": bpm,
                        "bars_per_segment": bars_per_segment,
                        "beats_per_segment": beats_per_segment,
                    },
                )
            )
            seg_idx += 1

        if not segments:
            # Fallback: single segment
            segments.append(
                AudioSegment(
                    title="Full Track",
                    start_time=0.0,
                    end_time=total_duration,
                    detection_method="bpm",
                    confidence=0.5,
                    metadata={"bpm": bpm},
                )
            )

        return segments

    # ------------------------------------------------------------------
    # Strategy: hybrid
    # ------------------------------------------------------------------

    def _detect_hybrid(self, path: Path, **kwargs: Any) -> List[AudioSegment]:
        """Try embedded chapters first, then fall back to silence detection.

        Parameters
        ----------
        path:
            Path to the audio file.

        Returns
        -------
        list[AudioSegment]
        """
        # Attempt 1: embedded chapters (does not require pydub)
        if _HAS_MUTAGEN:
            try:
                segments = self._detect_from_chapters(path, **kwargs)
                if segments:
                    self.logger.info("Hybrid: found %d embedded chapter(s)", len(segments))
                    return segments
            except DetectionError:
                self.logger.debug("Hybrid: no embedded chapters, trying silence...")

        # Attempt 2: CUE sheet sibling
        cue_candidate = path.with_suffix(".cue")
        if cue_candidate.is_file():
            try:
                segments = self._detect_from_cue(path, cue_path=str(cue_candidate), **kwargs)
                if segments:
                    self.logger.info("Hybrid: found %d CUE track(s)", len(segments))
                    return segments
            except (DetectionError, ValueError):
                self.logger.debug("Hybrid: CUE parsing failed, trying silence...")

        # Attempt 3: silence detection
        if _HAS_PYDUB:
            try:
                segments = self._detect_from_silence(path, **kwargs)
                if segments:
                    self.logger.info("Hybrid: found %d silence-based segment(s)", len(segments))
                    return segments
            except DetectionError:
                self.logger.debug("Hybrid: silence detection failed")

        raise DetectionError(
            f"Hybrid detection exhausted all strategies for {path.name}. "
            "Ensure at least one of mutagen or pydub is installed.",
            path=str(path),
        )

    # ------------------------------------------------------------------
    # Audio info
    # ------------------------------------------------------------------

    def get_audio_info(self, path: Path) -> AudioInfo:
        """Gather metadata about an audio file.

        The method tries *mutagen* first for tag/codec information and falls
        back to *ffprobe* for duration and format details.

        Parameters
        ----------
        path:
            Path to the audio file.

        Returns
        -------
        AudioInfo
        """
        path = Path(path)
        if not path.is_file():
            raise DetectionError(f"File not found: {path}", path=str(path))

        file_size = path.stat().st_size

        # Defaults
        duration = 0.0
        codec = "unknown"
        bitrate = None  # type: Optional[int]
        sample_rate = 44100
        channels = 2
        tags = {}  # type: Dict[str, Any]
        format_name = "unknown"

        # -- mutagen ---------------------------------------------------------
        if _HAS_MUTAGEN:
            try:
                mf = mutagen.File(str(path), easy=True)
                if mf is not None:
                    if mf.info:
                        duration = getattr(mf.info, "length", 0.0) or 0.0
                        bitrate = getattr(mf.info, "bitrate", None)
                        sample_rate = getattr(mf.info, "sample_rate", 44100) or 44100
                        channels = getattr(mf.info, "channels", 2) or 2
                        codec = type(mf.info).__name__.lower()
                    if mf.tags:
                        for key in mf.tags:
                            val = mf.tags[key]
                            if isinstance(val, list):
                                tags[key] = [str(v) for v in val]
                            else:
                                tags[key] = str(val)
            except Exception as exc:
                self.logger.debug("mutagen probe failed: %s", exc)

        # -- ffprobe fallback ------------------------------------------------
        if duration <= 0:
            duration, ffprobe_info = self._ffprobe_info(path)
            if ffprobe_info:
                codec = ffprobe_info.get("codec", codec)
                bitrate = ffprobe_info.get("bitrate", bitrate)
                sample_rate = ffprobe_info.get("sample_rate", sample_rate)
                channels = ffprobe_info.get("channels", channels)
                format_name = ffprobe_info.get("format_name", format_name)

        # -- pydub as last resort for duration -------------------------------
        if duration <= 0 and _HAS_PYDUB:
            try:
                audio = PydubSegment.from_file(str(path))
                duration = len(audio) / 1000.0
            except Exception as exc:
                self.logger.debug("pydub duration probe failed: %s", exc)

        return AudioInfo(
            path=path,
            duration=duration,
            codec=codec,
            bitrate=bitrate,
            sample_rate=sample_rate,
            channels=channels,
            tags=tags,
            file_size=file_size,
            format_name=format_name,
        )

    @staticmethod
    def _ffprobe_info(path: Path) -> Tuple[float, Dict[str, Any]]:
        """Run *ffprobe* and return ``(duration, info_dict)``."""
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v", "quiet",
                    "-print_format", "json",
                    "-show_format",
                    "-show_streams",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return 0.0, {}

        if result.returncode != 0:
            return 0.0, {}

        try:
            data = json.loads(result.stdout)
        except (json.JSONDecodeError, ValueError):
            return 0.0, {}

        info: Dict[str, Any] = {}

        # Format-level metadata
        fmt = data.get("format", {})
        duration = float(fmt.get("duration", 0))
        info["format_name"] = fmt.get("format_long_name", fmt.get("format_name", "unknown"))
        fmt_bitrate = fmt.get("bit_rate")
        if fmt_bitrate is not None:
            info["bitrate"] = int(fmt_bitrate)

        # First audio stream
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "audio":
                info["codec"] = stream.get("codec_name", "unknown")
                sr = stream.get("sample_rate")
                if sr is not None:
                    info["sample_rate"] = int(sr)
                ch = stream.get("channels")
                if ch is not None:
                    info["channels"] = int(ch)
                if duration <= 0:
                    duration = float(stream.get("duration", 0))
                break

        return duration, info
