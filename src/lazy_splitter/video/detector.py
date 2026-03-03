"""Video chapter and scene boundary detection.

This module provides :class:`VideoChapterDetector`, which can locate segment
boundaries inside video files using several strategies:

* **chapters** -- read embedded chapter metadata via ``ffprobe``.
* **scenes** -- detect visual scene changes with PySceneDetect.
* **silence** -- find silent gaps in the audio track via FFmpeg.
* **timestamps** -- accept a user-supplied list of split points.
* **hybrid** -- combine multiple strategies and merge the results.

All external tool invocations (``ffprobe``, ``ffmpeg``) go through
:mod:`subprocess` with proper error handling and timeout support.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from lazy_splitter.core.base import BaseDetector
from lazy_splitter.core.exceptions import DetectionError
from lazy_splitter.core.models import DetectionResult
from lazy_splitter.video.models import VideoInfo, VideoSegment

# Optional dependency -- gracefully degrade when not installed.
try:
    from scenedetect import ContentDetector, SceneManager, open_video  # type: ignore[import-untyped]

    _HAS_SCENEDETECT = True
except ImportError:  # pragma: no cover
    _HAS_SCENEDETECT = False

logger = logging.getLogger(__name__)

# Supported container formats for quick sanity checks.
_VIDEO_EXTENSIONS = frozenset({
    ".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".wmv",
    ".m4v", ".ts", ".mts", ".m2ts", ".ogv", ".3gp",
})


def _check_tool(name: str) -> str:
    """Return the absolute path to *name* or raise :class:`DetectionError`.

    Parameters
    ----------
    name:
        The executable name (e.g. ``"ffprobe"``).

    Returns
    -------
    str
        Resolved path to the tool.

    Raises
    ------
    DetectionError
        If the tool is not found on ``$PATH``.
    """
    path = shutil.which(name)
    if path is None:
        raise DetectionError(
            f"{name!r} is not installed or not on $PATH. "
            f"Please install FFmpeg to use video detection.",
            tool=name,
        )
    return path


def _run_ffprobe(args: List[str], *, timeout: int = 60) -> str:
    """Run ``ffprobe`` with the given arguments and return stdout.

    Parameters
    ----------
    args:
        Extra arguments passed *after* ``ffprobe``.
    timeout:
        Maximum wall-clock seconds before the process is killed.

    Returns
    -------
    str
        The captured standard output.

    Raises
    ------
    DetectionError
        On non-zero exit code or timeout.
    """
    ffprobe = _check_tool("ffprobe")
    cmd = [ffprobe, "-v", "quiet"] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise DetectionError(
            f"ffprobe timed out after {timeout}s",
            command=" ".join(cmd),
        ) from exc
    except OSError as exc:
        raise DetectionError(
            f"Failed to execute ffprobe: {exc}",
            command=" ".join(cmd),
        ) from exc

    if result.returncode != 0:
        raise DetectionError(
            f"ffprobe exited with code {result.returncode}: "
            f"{result.stderr.strip()}",
            command=" ".join(cmd),
        )
    return result.stdout


def _run_ffmpeg(args: List[str], *, timeout: int = 300) -> str:
    """Run ``ffmpeg`` with the given arguments and return stderr.

    FFmpeg writes diagnostic output (including filter results such as
    ``silencedetect`` and ``blackdetect``) to *stderr*, so that is what
    we capture and return.

    Parameters
    ----------
    args:
        Extra arguments passed *after* ``ffmpeg``.
    timeout:
        Maximum wall-clock seconds before the process is killed.

    Returns
    -------
    str
        The captured standard error.

    Raises
    ------
    DetectionError
        On non-zero exit code or timeout.
    """
    ffmpeg = _check_tool("ffmpeg")
    cmd = [ffmpeg, "-y"] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise DetectionError(
            f"ffmpeg timed out after {timeout}s",
            command=" ".join(cmd),
        ) from exc
    except OSError as exc:
        raise DetectionError(
            f"Failed to execute ffmpeg: {exc}",
            command=" ".join(cmd),
        ) from exc

    # ffmpeg may exit 0 even when partially failing; for detection we only
    # care about the filter output on stderr, so we do *not* check the
    # return code strictly here (some filters intentionally produce no
    # output frames, which causes a non-zero exit).
    return result.stderr


class VideoChapterDetector(BaseDetector):
    """Detect segment boundaries in video files.

    Supported strategies
    --------------------
    chapters
        Read embedded chapter metadata from MKV / MP4 containers.
    scenes
        Use PySceneDetect's :class:`ContentDetector` to find visual
        scene changes.  Requires the optional ``scenedetect`` package.
    silence
        Use FFmpeg's ``silencedetect`` audio filter to locate silent
        gaps that typically separate logical segments.
    timestamps
        Accept a caller-supplied list of timestamps (in seconds) and
        convert them into segment descriptors.
    hybrid
        Run *chapters* first; fall back to *scenes* + *silence* if no
        chapters are found, then merge overlapping boundaries.

    Parameters
    ----------
    scene_threshold:
        Sensitivity for scene-change detection (lower = more sensitive).
        Passed to :class:`scenedetect.ContentDetector`.  Default ``27.0``.
    silence_threshold:
        Minimum silence level in dB for the ``silencedetect`` filter.
        Default ``-30``.
    silence_duration:
        Minimum silence duration in seconds.  Default ``0.5``.
    black_frame_threshold:
        Pixel-luminance ratio threshold for black-frame detection.
        Default ``0.98``.
    black_frame_duration:
        Minimum duration (seconds) for a run of black frames.
        Default ``0.1``.
    merge_tolerance:
        When merging results from multiple strategies (``hybrid``),
        boundaries within this many seconds of each other are treated
        as duplicates.  Default ``1.0``.
    logger:
        Optional :class:`logging.Logger` instance.
    """

    # Strategies that this detector supports.
    STRATEGIES = ("chapters", "scenes", "silence", "timestamps", "hybrid")

    def __init__(
        self,
        *,
        scene_threshold: float = 27.0,
        silence_threshold: float = -30,
        silence_duration: float = 0.5,
        black_frame_threshold: float = 0.98,
        black_frame_duration: float = 0.1,
        merge_tolerance: float = 1.0,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        super().__init__(logger=logger)
        self.scene_threshold = scene_threshold
        self.silence_threshold = silence_threshold
        self.silence_duration = silence_duration
        self.black_frame_threshold = black_frame_threshold
        self.black_frame_duration = black_frame_duration
        self.merge_tolerance = merge_tolerance

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(
        self,
        input_path: Path,
        strategy: str = "chapters",
        **kwargs: Any,
    ) -> DetectionResult:
        """Detect segments in the video at *input_path*.

        Parameters
        ----------
        input_path:
            Path to the input video file.
        strategy:
            Detection strategy name.  One of ``"chapters"``,
            ``"scenes"``, ``"silence"``, ``"timestamps"``, or
            ``"hybrid"``.
        **kwargs:
            Strategy-specific options.  For ``"timestamps"``, pass
            ``timestamps=<list of float>``.

        Returns
        -------
        DetectionResult
            Result containing the detected :class:`VideoSegment` list.

        Raises
        ------
        DetectionError
            If the file does not exist, is not a supported format, or
            the chosen strategy fails.
        """
        path = Path(input_path)
        self._validate_path(path)

        if strategy not in self.STRATEGIES:
            raise DetectionError(
                f"Unknown detection strategy {strategy!r}; "
                f"choose from {self.STRATEGIES}",
                strategy=strategy,
            )

        self.logger.info(
            "Detecting segments in %s using strategy=%r", path.name, strategy
        )

        if strategy == "chapters":
            segments = self._detect_from_chapters(path)
        elif strategy == "scenes":
            segments = self._detect_from_scenes(path, **kwargs)
        elif strategy == "silence":
            segments = self._detect_from_silence(path, **kwargs)
        elif strategy == "timestamps":
            timestamps = kwargs.get("timestamps")
            if timestamps is None:
                raise DetectionError(
                    "The 'timestamps' strategy requires a 'timestamps' "
                    "keyword argument (list of float).",
                    strategy=strategy,
                )
            segments = self._detect_from_timestamps(path, timestamps)
        elif strategy == "hybrid":
            segments = self._detect_hybrid(path, **kwargs)
        else:
            # Defensive -- should not reach here.
            segments = []  # pragma: no cover

        self.logger.info(
            "Detected %d segment(s) in %s", len(segments), path.name
        )

        return DetectionResult(
            segments=segments,
            strategy=strategy,
            source_path=path,
            metadata={"detector": self.__class__.__name__},
        )

    def get_video_info(self, path: Path) -> VideoInfo:
        """Retrieve comprehensive metadata for the video at *path*.

        Uses ``ffprobe`` to extract codec, resolution, duration, bitrate,
        frame rate, audio codec, chapter count, container format, and file
        size information.

        Parameters
        ----------
        path:
            Path to the video file.

        Returns
        -------
        VideoInfo
            A populated :class:`VideoInfo` dataclass.

        Raises
        ------
        DetectionError
            If ``ffprobe`` fails or the output cannot be parsed.
        """
        path = Path(path)
        self._validate_path(path)

        raw = _run_ffprobe([
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            "-show_chapters",
            str(path),
        ])

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DetectionError(
                f"Failed to parse ffprobe JSON output: {exc}",
                path=str(path),
            ) from exc

        # -- Locate the first video stream -----------------------------------
        video_stream: Dict[str, Any] = {}
        audio_stream: Dict[str, Any] = {}
        for stream in data.get("streams", []):
            codec_type = stream.get("codec_type", "")
            if codec_type == "video" and not video_stream:
                video_stream = stream
            elif codec_type == "audio" and not audio_stream:
                audio_stream = stream

        fmt = data.get("format", {})

        # -- Parse frame rate ------------------------------------------------
        fps = 0.0
        r_frame_rate = video_stream.get("r_frame_rate", "0/1")
        try:
            num, den = r_frame_rate.split("/")
            if int(den) != 0:
                fps = int(num) / int(den)
        except (ValueError, ZeroDivisionError):
            fps = 0.0

        return VideoInfo(
            path=path,
            duration=float(fmt.get("duration", 0)),
            width=int(video_stream.get("width", 0)),
            height=int(video_stream.get("height", 0)),
            codec=video_stream.get("codec_name", "unknown"),
            bitrate=int(fmt.get("bit_rate", 0)),
            fps=fps,
            audio_codec=audio_stream.get("codec_name"),
            chapters_count=len(data.get("chapters", [])),
            format_name=fmt.get("format_name", ""),
            file_size=int(fmt.get("size", 0)),
        )

    # ------------------------------------------------------------------
    # Private detection strategies
    # ------------------------------------------------------------------

    def _detect_from_chapters(self, path: Path) -> List[VideoSegment]:
        """Read embedded chapter metadata from MKV/MP4 via ffprobe.

        Parameters
        ----------
        path:
            Path to the video file.

        Returns
        -------
        list of VideoSegment
            One segment per embedded chapter.  Returns an empty list if
            the container has no chapter metadata.
        """
        raw = _run_ffprobe([
            "-print_format", "json",
            "-show_chapters",
            str(path),
        ])

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DetectionError(
                f"Failed to parse ffprobe chapters output: {exc}",
                path=str(path),
            ) from exc

        chapters = data.get("chapters", [])
        if not chapters:
            self.logger.debug("No embedded chapters found in %s", path.name)
            return []

        segments: List[VideoSegment] = []
        for idx, ch in enumerate(chapters):
            title = ch.get("tags", {}).get("title", f"Chapter {idx + 1}")
            start = float(ch.get("start_time", 0))
            end = float(ch.get("end_time", 0))
            segments.append(
                VideoSegment(
                    title=title,
                    start_time=start,
                    end_time=end,
                    detection_method="chapters",
                    confidence=1.0,
                    metadata={"chapter_index": idx},
                )
            )

        self.logger.debug(
            "Found %d embedded chapter(s) in %s", len(segments), path.name
        )
        return segments

    def _detect_from_scenes(
        self,
        path: Path,
        *,
        threshold: Optional[float] = None,
        min_scene_len: int = 15,
        **kwargs: Any,
    ) -> List[VideoSegment]:
        """Detect scene changes using PySceneDetect's ContentDetector.

        Parameters
        ----------
        path:
            Path to the video file.
        threshold:
            Scene-change sensitivity.  Overrides the instance default
            ``scene_threshold`` for this call.
        min_scene_len:
            Minimum scene length in frames.
        **kwargs:
            Ignored (absorbed for compatibility with ``detect()``).

        Returns
        -------
        list of VideoSegment
            One segment per detected scene.

        Raises
        ------
        DetectionError
            If PySceneDetect is not installed.
        """
        if not _HAS_SCENEDETECT:
            raise DetectionError(
                "PySceneDetect is required for scene detection but is not "
                "installed.  Install it with: pip install scenedetect[opencv]",
            )

        effective_threshold = threshold if threshold is not None else self.scene_threshold

        self.logger.debug(
            "Running scene detection on %s (threshold=%.1f, min_scene_len=%d)",
            path.name,
            effective_threshold,
            min_scene_len,
        )

        try:
            video = open_video(str(path))
            scene_manager = SceneManager()
            scene_manager.add_detector(
                ContentDetector(
                    threshold=effective_threshold,
                    min_scene_len=min_scene_len,
                )
            )
            scene_manager.detect_scenes(video)
            scene_list = scene_manager.get_scene_list()
        except Exception as exc:
            raise DetectionError(
                f"Scene detection failed: {exc}",
                path=str(path),
            ) from exc

        segments: List[VideoSegment] = []
        for idx, (start_tc, end_tc) in enumerate(scene_list):
            start_sec = start_tc.get_seconds()
            end_sec = end_tc.get_seconds()
            segments.append(
                VideoSegment(
                    title=f"Scene {idx + 1}",
                    start_time=start_sec,
                    end_time=end_sec,
                    detection_method="scenes",
                    confidence=0.8,
                    metadata={"scene_index": idx},
                )
            )

        self.logger.debug(
            "Detected %d scene(s) in %s", len(segments), path.name
        )
        return segments

    def _detect_from_silence(
        self,
        path: Path,
        *,
        silence_threshold: Optional[float] = None,
        silence_duration: Optional[float] = None,
        **kwargs: Any,
    ) -> List[VideoSegment]:
        """Find silent gaps using FFmpeg's ``silencedetect`` filter.

        Silent gaps are interpreted as boundaries between segments: the
        audio *between* silences becomes the content of each segment.

        Parameters
        ----------
        path:
            Path to the video file.
        silence_threshold:
            Silence level in dB.  Overrides the instance default.
        silence_duration:
            Minimum silence duration in seconds.  Overrides the instance
            default.
        **kwargs:
            Ignored (absorbed for compatibility with ``detect()``).

        Returns
        -------
        list of VideoSegment
            Segments derived from the regions between detected silences.
        """
        eff_threshold = (
            silence_threshold
            if silence_threshold is not None
            else self.silence_threshold
        )
        eff_duration = (
            silence_duration
            if silence_duration is not None
            else self.silence_duration
        )

        filter_str = (
            f"silencedetect=noise={eff_threshold}dB:d={eff_duration}"
        )

        stderr = _run_ffmpeg([
            "-i", str(path),
            "-af", filter_str,
            "-f", "null",
            "-",
        ])

        # Parse silencedetect output lines:
        #   [silencedetect @ 0x...] silence_start: 12.345
        #   [silencedetect @ 0x...] silence_end: 13.678 | silence_duration: 1.333
        silence_starts: List[float] = []
        silence_ends: List[float] = []

        for line in stderr.splitlines():
            start_match = re.search(r"silence_start:\s*([\d.]+)", line)
            if start_match:
                silence_starts.append(float(start_match.group(1)))
            end_match = re.search(r"silence_end:\s*([\d.]+)", line)
            if end_match:
                silence_ends.append(float(end_match.group(1)))

        if not silence_starts:
            self.logger.debug(
                "No silence detected in %s with threshold=%sdB, duration=%ss",
                path.name,
                eff_threshold,
                eff_duration,
            )
            return []

        # Derive the total duration so we can bound the last segment.
        info = self.get_video_info(path)
        total_duration = info.duration

        # Build segments from the gaps *between* silences.
        split_points: List[float] = []
        for s_start, s_end in zip(silence_starts, silence_ends):
            midpoint = (s_start + s_end) / 2.0
            split_points.append(midpoint)

        return self._split_points_to_segments(
            split_points,
            total_duration,
            detection_method="silence",
            confidence=0.7,
        )

    def _detect_from_timestamps(
        self,
        path: Path,
        timestamps: Sequence[float],
    ) -> List[VideoSegment]:
        """Convert user-provided timestamps into segment descriptors.

        Parameters
        ----------
        path:
            Path to the video file (used to determine total duration).
        timestamps:
            Ordered list of split points in seconds.

        Returns
        -------
        list of VideoSegment
        """
        if not timestamps:
            return []

        info = self.get_video_info(path)
        total_duration = info.duration

        sorted_ts = sorted(set(timestamps))

        return self._split_points_to_segments(
            list(sorted_ts),
            total_duration,
            detection_method="timestamps",
            confidence=1.0,
        )

    def _detect_black_frames(
        self,
        path: Path,
        *,
        threshold: Optional[float] = None,
        duration: Optional[float] = None,
    ) -> List[Dict[str, float]]:
        """Detect runs of black frames using FFmpeg's ``blackdetect`` filter.

        This is a low-level helper used by the hybrid strategy; it returns
        raw interval data rather than :class:`VideoSegment` objects.

        Parameters
        ----------
        path:
            Path to the video file.
        threshold:
            Pixel-luminance ratio threshold (0.0 -- 1.0).  Overrides
            the instance default ``black_frame_threshold``.
        duration:
            Minimum black-frame duration in seconds.  Overrides the
            instance default ``black_frame_duration``.

        Returns
        -------
        list of dict
            Each dict has keys ``"start"``, ``"end"``, and ``"duration"``
            (all floats in seconds).
        """
        eff_threshold = (
            threshold
            if threshold is not None
            else self.black_frame_threshold
        )
        eff_duration = (
            duration
            if duration is not None
            else self.black_frame_duration
        )

        filter_str = (
            f"blackdetect=d={eff_duration}:pix_th={eff_threshold}"
        )

        stderr = _run_ffmpeg([
            "-i", str(path),
            "-vf", filter_str,
            "-an",
            "-f", "null",
            "-",
        ])

        # Parse blackdetect output lines:
        #   [blackdetect @ 0x...] black_start:0 black_end:1.5 black_duration:1.5
        results: List[Dict[str, float]] = []
        for line in stderr.splitlines():
            match = re.search(
                r"black_start:\s*([\d.]+)\s+"
                r"black_end:\s*([\d.]+)\s+"
                r"black_duration:\s*([\d.]+)",
                line,
            )
            if match:
                results.append({
                    "start": float(match.group(1)),
                    "end": float(match.group(2)),
                    "duration": float(match.group(3)),
                })

        self.logger.debug(
            "Detected %d black-frame region(s) in %s",
            len(results),
            path.name,
        )
        return results

    def _detect_hybrid(self, path: Path, **kwargs: Any) -> List[VideoSegment]:
        """Run multiple strategies and merge the results.

        The hybrid approach tries embedded chapters first.  If none are
        found, it combines scene detection (if available), silence
        detection, and black-frame detection, then de-duplicates
        boundaries that are within ``merge_tolerance`` seconds of each
        other.

        Parameters
        ----------
        path:
            Path to the video file.
        **kwargs:
            Forwarded to individual strategy methods.

        Returns
        -------
        list of VideoSegment
        """
        # 1. Try embedded chapters -- most reliable.
        chapters = self._detect_from_chapters(path)
        if chapters:
            self.logger.debug(
                "Hybrid: using embedded chapters (%d found)", len(chapters)
            )
            return chapters

        # 2. Gather split points from multiple sources.
        split_points: List[float] = []

        # Scene detection (optional dependency).
        if _HAS_SCENEDETECT:
            try:
                scene_segments = self._detect_from_scenes(path, **kwargs)
                for seg in scene_segments:
                    if seg.start_time > 0:
                        split_points.append(seg.start_time)
            except DetectionError:
                self.logger.debug(
                    "Hybrid: scene detection failed; skipping.", exc_info=True
                )

        # Silence detection.
        try:
            silence_segments = self._detect_from_silence(path, **kwargs)
            for seg in silence_segments:
                if seg.start_time > 0:
                    split_points.append(seg.start_time)
        except DetectionError:
            self.logger.debug(
                "Hybrid: silence detection failed; skipping.", exc_info=True
            )

        # Black-frame detection.
        try:
            black_regions = self._detect_black_frames(path)
            for region in black_regions:
                midpoint = (region["start"] + region["end"]) / 2.0
                if midpoint > 0:
                    split_points.append(midpoint)
        except DetectionError:
            self.logger.debug(
                "Hybrid: black-frame detection failed; skipping.",
                exc_info=True,
            )

        if not split_points:
            self.logger.info(
                "Hybrid: no boundaries detected in %s", path.name
            )
            return []

        # 3. De-duplicate / merge nearby points.
        merged = self._merge_split_points(
            sorted(split_points), self.merge_tolerance
        )

        info = self.get_video_info(path)
        return self._split_points_to_segments(
            merged,
            info.duration,
            detection_method="hybrid",
            confidence=0.6,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_path(self, path: Path) -> None:
        """Raise :class:`DetectionError` if *path* is not a valid video file."""
        if not path.exists():
            raise DetectionError(
                f"File not found: {path}",
                path=str(path),
            )
        if not path.is_file():
            raise DetectionError(
                f"Not a file: {path}",
                path=str(path),
            )
        if path.suffix.lower() not in _VIDEO_EXTENSIONS:
            raise DetectionError(
                f"Unsupported video format {path.suffix!r}. "
                f"Supported: {sorted(_VIDEO_EXTENSIONS)}",
                path=str(path),
                extension=path.suffix,
            )

    @staticmethod
    def _merge_split_points(
        points: List[float], tolerance: float
    ) -> List[float]:
        """Merge split points that are within *tolerance* seconds of each other.

        Parameters
        ----------
        points:
            Sorted list of candidate split-point timestamps.
        tolerance:
            Maximum distance (seconds) at which two points are
            considered duplicates.

        Returns
        -------
        list of float
            De-duplicated and sorted split points.
        """
        if not points:
            return []

        merged: List[float] = [points[0]]
        for pt in points[1:]:
            if pt - merged[-1] > tolerance:
                merged.append(pt)
            else:
                # Keep the average of the cluster.
                merged[-1] = (merged[-1] + pt) / 2.0
        return merged

    @staticmethod
    def _split_points_to_segments(
        split_points: List[float],
        total_duration: float,
        detection_method: str,
        confidence: float,
    ) -> List[VideoSegment]:
        """Convert an ordered list of split points into :class:`VideoSegment` objects.

        Parameters
        ----------
        split_points:
            Sorted boundary timestamps in seconds (exclusive of 0 and
            *total_duration*).
        total_duration:
            Total duration of the source file in seconds.
        detection_method:
            Value for :attr:`VideoSegment.detection_method`.
        confidence:
            Value for :attr:`VideoSegment.confidence`.

        Returns
        -------
        list of VideoSegment
        """
        if not split_points:
            return []

        boundaries = [0.0] + list(split_points) + [total_duration]
        segments: List[VideoSegment] = []

        for idx in range(len(boundaries) - 1):
            start = boundaries[idx]
            end = boundaries[idx + 1]
            if end <= start:
                continue
            segments.append(
                VideoSegment(
                    title=f"Segment {idx + 1}",
                    start_time=start,
                    end_time=end,
                    detection_method=detection_method,
                    confidence=confidence,
                    metadata={"segment_index": idx},
                )
            )

        return segments
