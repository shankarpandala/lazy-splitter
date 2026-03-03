"""Video splitting engine.

This module provides :class:`VideoSplitter`, which splits a video file into
multiple segments using FFmpeg.  It supports:

* **Lossless stream copy** -- ultra-fast splitting without re-encoding.
* **Re-encode** -- transcoding to a different codec, resolution, or quality.
* **Thumbnail generation** -- extracting a representative frame per segment.
* **Progress callbacks** -- reporting split progress to callers / UIs.

Split points can originate from any :class:`VideoChapterDetector` strategy
(chapters, scenes, silence, timestamps, hybrid) or be computed on-the-fly
from a target duration or file-size budget.
"""

from __future__ import annotations

import json
import logging
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from lazy_splitter.core.base import BaseSplitter
from lazy_splitter.core.exceptions import SplitError
from lazy_splitter.core.models import DetectionResult
from lazy_splitter.core.utils import ensure_dir, format_duration, sanitize_filename
from lazy_splitter.video.models import VideoInfo, VideoSegment, VideoSplitOptions

logger = logging.getLogger(__name__)


def _check_tool(name: str) -> str:
    """Return the absolute path to *name* or raise :class:`SplitError`.

    Parameters
    ----------
    name:
        Executable name (e.g. ``"ffmpeg"``).

    Returns
    -------
    str
        Resolved path to the tool.

    Raises
    ------
    SplitError
        If the tool is not found on ``$PATH``.
    """
    path = shutil.which(name)
    if path is None:
        raise SplitError(
            f"{name!r} is not installed or not on $PATH. "
            f"Please install FFmpeg to use the video splitter.",
            tool=name,
        )
    return path


def _run_ffmpeg_split(
    args: List[str],
    *,
    timeout: int = 600,
) -> subprocess.CompletedProcess:  # type: ignore[type-arg]
    """Execute an ``ffmpeg`` command for a split operation.

    Parameters
    ----------
    args:
        Full argument list **including** the ``ffmpeg`` executable.
    timeout:
        Maximum wall-clock seconds.

    Returns
    -------
    subprocess.CompletedProcess

    Raises
    ------
    SplitError
        On non-zero exit or timeout.
    """
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise SplitError(
            f"ffmpeg timed out after {timeout}s",
            command=" ".join(args),
        ) from exc
    except OSError as exc:
        raise SplitError(
            f"Failed to execute ffmpeg: {exc}",
            command=" ".join(args),
        ) from exc

    if result.returncode != 0:
        raise SplitError(
            f"ffmpeg exited with code {result.returncode}: "
            f"{result.stderr.strip()[:500]}",
            command=" ".join(args),
        )

    return result


def _run_ffprobe_json(args: List[str], *, timeout: int = 60) -> Dict[str, Any]:
    """Run ``ffprobe`` and return parsed JSON output.

    Parameters
    ----------
    args:
        Extra arguments passed *after* ``ffprobe -v quiet``.
    timeout:
        Maximum wall-clock seconds.

    Returns
    -------
    dict
        Parsed JSON data.

    Raises
    ------
    SplitError
        On failure.
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
        raise SplitError(
            f"ffprobe timed out after {timeout}s",
            command=" ".join(cmd),
        ) from exc
    except OSError as exc:
        raise SplitError(
            f"Failed to execute ffprobe: {exc}",
            command=" ".join(cmd),
        ) from exc

    if result.returncode != 0:
        raise SplitError(
            f"ffprobe exited with code {result.returncode}: "
            f"{result.stderr.strip()[:500]}",
            command=" ".join(cmd),
        )

    try:
        return json.loads(result.stdout)  # type: ignore[no-any-return]
    except json.JSONDecodeError as exc:
        raise SplitError(
            f"Failed to parse ffprobe JSON: {exc}",
            command=" ".join(cmd),
        ) from exc


# Supported container formats.
_VIDEO_EXTENSIONS = frozenset({
    ".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".wmv",
    ".m4v", ".ts", ".mts", ".m2ts", ".ogv", ".3gp",
})

# Map from short codec names to preferred container extensions.
_CODEC_CONTAINER_MAP: Dict[str, str] = {
    "copy": "",  # Determined from input.
    "h264": ".mp4",
    "h265": ".mp4",
    "vp9": ".webm",
    "av1": ".mkv",
}


class VideoSplitter(BaseSplitter):
    """Split video files into segments using FFmpeg.

    The splitter supports both lossless stream-copy mode and full
    re-encoding.  It can generate thumbnail images for each segment and
    report progress through an optional callback.

    Parameters
    ----------
    default_options:
        Default :class:`VideoSplitOptions` to use when none are
        provided to :meth:`split`.
    thumbnail_enabled:
        Whether to generate a thumbnail for each output segment.
    thumbnail_time_offset:
        Offset in seconds from the segment start at which the
        thumbnail frame is captured.
    ffmpeg_timeout:
        Per-segment FFmpeg timeout in seconds.
    logger:
        Optional :class:`logging.Logger`.
    """

    def __init__(
        self,
        *,
        default_options: Optional[VideoSplitOptions] = None,
        thumbnail_enabled: bool = False,
        thumbnail_time_offset: float = 1.0,
        ffmpeg_timeout: int = 600,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        super().__init__(logger=logger)
        self.default_options = default_options or VideoSplitOptions()
        self.thumbnail_enabled = thumbnail_enabled
        self.thumbnail_time_offset = thumbnail_time_offset
        self.ffmpeg_timeout = ffmpeg_timeout

    # ------------------------------------------------------------------
    # Abstract interface implementation
    # ------------------------------------------------------------------

    @property
    def supported_extensions(self) -> List[str]:
        """File extensions this splitter can handle.

        Returns
        -------
        list of str
            Video container extensions including the leading dot.
        """
        return sorted(_VIDEO_EXTENSIONS)

    def preview(
        self,
        input_path: Path,
        **kwargs: Any,
    ) -> DetectionResult:
        """Preview what the splitter would produce without writing files.

        Delegates to :class:`VideoChapterDetector` to detect segments
        and returns the detection result for user confirmation.

        Parameters
        ----------
        input_path:
            Path to the source video file.
        **kwargs:
            Forwarded to the detector's :meth:`detect` method.  Accepts
            ``strategy`` (default ``"chapters"``).

        Returns
        -------
        DetectionResult
            Detected segments that *would* be created.
        """
        from lazy_splitter.video.detector import VideoChapterDetector

        strategy = kwargs.pop("strategy", "chapters")
        detector = VideoChapterDetector(logger=self.logger)
        return detector.detect(Path(input_path), strategy=strategy, **kwargs)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def split(
        self,
        input_path: Path,
        chapters: Sequence[Any],
        **kwargs: Any,
    ) -> List[Path]:
        """Split the video at *input_path* into the given *chapters*.

        Parameters
        ----------
        input_path:
            Path to the source video file.
        chapters:
            Sequence of :class:`VideoSegment` descriptors (or dicts
            with ``start_time`` / ``end_time`` keys).
        **kwargs:
            Optional keyword arguments:

            - ``output_dir`` (:class:`Path`): directory for output
              files.  Created if it does not exist.  Defaults to a
              subdirectory next to the source file.
            - ``progress_callback`` (callable): ``(current, total)``
              callback invoked after each segment is written.
            - Any :class:`VideoSplitOptions` field name to override
              the default (e.g. ``codec="h265"``,
              ``quality_preset="slow"``).

        Returns
        -------
        list of Path
            Paths to the newly created segment files.

        Raises
        ------
        SplitError
            If FFmpeg is missing, the file is invalid, or any segment
            fails to write.
        """
        path = Path(input_path)
        self._validate_path(path)
        _check_tool("ffmpeg")

        if not chapters:
            raise SplitError(
                "No segments provided for splitting.",
                path=str(path),
            )

        # Extract non-option kwargs.
        output_dir: Optional[Path] = kwargs.pop("output_dir", None)
        progress_callback: Optional[Callable[[int, int], None]] = kwargs.pop(
            "progress_callback", None
        )

        # Build effective options from remaining kwargs.
        options = self._build_options(**kwargs)

        # Resolve output directory.
        if output_dir is None:
            output_dir = path.parent / f"{path.stem}_segments"
        output_dir = ensure_dir(Path(output_dir))

        # Determine output extension.
        out_ext = self._resolve_extension(path, options)

        total = len(chapters)
        output_files: List[Path] = []

        self.logger.info(
            "Splitting %s into %d segment(s) (codec=%s) -> %s",
            path.name,
            total,
            options.codec,
            output_dir,
        )

        for idx, segment in enumerate(chapters):
            seg = self._coerce_segment(segment, idx)
            seg_name = sanitize_filename(seg.title) or f"segment_{idx + 1:03d}"
            out_path = output_dir / f"{seg_name}{out_ext}"

            # Avoid overwriting: append index if name collides.
            if out_path.exists():
                out_path = output_dir / f"{seg_name}_{idx + 1:03d}{out_ext}"

            self.logger.debug(
                "Writing segment %d/%d: %s (%.2fs -> %.2fs)",
                idx + 1,
                total,
                out_path.name,
                seg.start_time,
                seg.end_time,
            )

            if options.needs_reencode:
                self._split_reencode(
                    path, seg, out_path, options,
                )
            else:
                self._split_copy(path, seg, out_path, options)

            # Optional thumbnail.
            if self.thumbnail_enabled:
                thumb_path = self._generate_thumbnail(
                    path, seg, output_dir, idx
                )
                seg.thumbnail_path = thumb_path

            output_files.append(out_path)

            if progress_callback is not None:
                progress_callback(idx + 1, total)

        self.logger.info(
            "Successfully wrote %d segment(s) to %s",
            len(output_files),
            output_dir,
        )

        return output_files

    def split_by_duration(
        self,
        path: Path,
        max_duration: float,
        output_dir: Optional[Path] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        **kwargs: Any,
    ) -> List[Path]:
        """Split a video into equal-length segments of at most *max_duration* seconds.

        Parameters
        ----------
        path:
            Path to the source video.
        max_duration:
            Maximum duration per segment in seconds.
        output_dir:
            Output directory.
        progress_callback:
            Optional progress callback.
        **kwargs:
            Forwarded to :meth:`split` / :class:`VideoSplitOptions`.

        Returns
        -------
        list of Path
        """
        if max_duration <= 0:
            raise SplitError(
                "max_duration must be positive.",
                max_duration=max_duration,
            )

        info = self._get_video_info(path)
        total_duration = info.duration

        num_segments = max(1, math.ceil(total_duration / max_duration))
        segments: List[VideoSegment] = []

        for i in range(num_segments):
            start = i * max_duration
            end = min((i + 1) * max_duration, total_duration)
            segments.append(
                VideoSegment(
                    title=f"Part {i + 1}",
                    start_time=start,
                    end_time=end,
                    detection_method="duration",
                    confidence=1.0,
                )
            )

        return self.split(
            path,
            segments,
            output_dir=output_dir,
            progress_callback=progress_callback,
            **kwargs,
        )

    def split_by_size(
        self,
        path: Path,
        max_size_bytes: int,
        output_dir: Optional[Path] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        **kwargs: Any,
    ) -> List[Path]:
        """Split a video so each segment is approximately *max_size_bytes*.

        The segment duration is estimated from the overall bitrate.  Because
        actual encoded sizes vary, results are approximate.

        Parameters
        ----------
        path:
            Path to the source video.
        max_size_bytes:
            Target maximum file size in bytes per segment.
        output_dir:
            Output directory.
        progress_callback:
            Optional progress callback.
        **kwargs:
            Forwarded to :meth:`split` / :class:`VideoSplitOptions`.

        Returns
        -------
        list of Path
        """
        if max_size_bytes <= 0:
            raise SplitError(
                "max_size_bytes must be positive.",
                max_size_bytes=max_size_bytes,
            )

        info = self._get_video_info(path)

        if info.bitrate <= 0:
            raise SplitError(
                "Cannot determine bitrate; unable to estimate segment sizes.",
                path=str(path),
            )

        # bytes_per_second = bitrate (bits/s) / 8
        bytes_per_second = info.bitrate / 8.0
        max_duration = max_size_bytes / bytes_per_second

        return self.split_by_duration(
            path,
            max_duration,
            output_dir=output_dir,
            progress_callback=progress_callback,
            **kwargs,
        )

    def split_by_count(
        self,
        path: Path,
        count: int,
        output_dir: Optional[Path] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        **kwargs: Any,
    ) -> List[Path]:
        """Split a video into *count* equal-length segments.

        Parameters
        ----------
        path:
            Path to the source video.
        count:
            Number of segments to produce.
        output_dir:
            Output directory.
        progress_callback:
            Optional progress callback.
        **kwargs:
            Forwarded to :meth:`split` / :class:`VideoSplitOptions`.

        Returns
        -------
        list of Path
        """
        if count <= 0:
            raise SplitError("count must be positive.", count=count)

        info = self._get_video_info(path)
        segment_duration = info.duration / count

        return self.split_by_duration(
            path,
            segment_duration,
            output_dir=output_dir,
            progress_callback=progress_callback,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # Private: core split methods
    # ------------------------------------------------------------------

    def _split_copy(
        self,
        source: Path,
        segment: VideoSegment,
        output: Path,
        options: VideoSplitOptions,
    ) -> None:
        """Lossless stream-copy split.

        Copies the video/audio streams without re-encoding, which is
        extremely fast but can only split on keyframe boundaries.  The
        ``-ss`` seek is placed *before* ``-i`` for fast input seeking,
        and ``-avoid_negative_ts make_zero`` is used to prevent
        timestamp discontinuities.

        Parameters
        ----------
        source:
            Input video path.
        segment:
            The segment to extract.
        output:
            Output file path.
        options:
            Split options (subtitle handling is honoured).
        """
        ffmpeg = _check_tool("ffmpeg")
        duration = segment.end_time - segment.start_time

        cmd: List[str] = [
            ffmpeg, "-y",
            "-ss", str(segment.start_time),
            "-i", str(source),
            "-t", str(duration),
            "-c:v", "copy",
            "-c:a", "copy",
        ]

        # Subtitle handling.
        if options.subtitle_handling == "copy":
            cmd.extend(["-c:s", "copy"])
        elif options.subtitle_handling == "drop":
            cmd.append("-sn")

        cmd.extend([
            "-avoid_negative_ts", "make_zero",
            "-map_metadata", "0",
            str(output),
        ])

        _run_ffmpeg_split(cmd, timeout=self.ffmpeg_timeout)

    def _split_reencode(
        self,
        source: Path,
        segment: VideoSegment,
        output: Path,
        options: VideoSplitOptions,
    ) -> None:
        """Re-encode split with configurable codec and quality.

        This method allows frame-accurate cuts (not limited to
        keyframe boundaries) and can change the codec, resolution,
        or quality of the output.

        Parameters
        ----------
        source:
            Input video path.
        segment:
            The segment to extract.
        output:
            Output file path.
        options:
            Split options controlling codec, preset, resolution, etc.
        """
        ffmpeg = _check_tool("ffmpeg")
        duration = segment.end_time - segment.start_time

        cmd: List[str] = [
            ffmpeg, "-y",
            "-ss", str(segment.start_time),
            "-i", str(source),
            "-t", str(duration),
        ]

        # Apply codec/quality/resolution arguments.
        cmd.extend(options.to_ffmpeg_args())

        # Handle subtitle burning (requires a video filter).
        if options.subtitle_handling == "burn":
            # If a scale filter is already present, we chain the subtitles
            # filter onto it.  Otherwise we add it standalone.
            has_vf = "-vf" in cmd
            if has_vf:
                vf_idx = cmd.index("-vf") + 1
                cmd[vf_idx] = cmd[vf_idx] + f",subtitles='{source}'"
            else:
                cmd.extend(["-vf", f"subtitles='{source}'"])

        cmd.extend([
            "-avoid_negative_ts", "make_zero",
            str(output),
        ])

        _run_ffmpeg_split(cmd, timeout=self.ffmpeg_timeout)

    # ------------------------------------------------------------------
    # Private: thumbnail generation
    # ------------------------------------------------------------------

    def _generate_thumbnail(
        self,
        source: Path,
        segment: VideoSegment,
        output_dir: Path,
        index: int,
    ) -> Optional[Path]:
        """Generate a JPEG thumbnail for a segment.

        Captures a single frame at ``segment.start_time +
        thumbnail_time_offset`` (clamped to the segment duration).

        Parameters
        ----------
        source:
            Source video file.
        segment:
            The segment whose thumbnail to generate.
        output_dir:
            Directory to write the thumbnail into.
        index:
            Segment index (for naming).

        Returns
        -------
        Path or None
            Path to the generated thumbnail, or ``None`` on failure.
        """
        thumb_dir = ensure_dir(output_dir / "thumbnails")
        thumb_path = thumb_dir / f"thumb_{index + 1:03d}.jpg"

        # Clamp the offset so it does not exceed the segment.
        offset = min(self.thumbnail_time_offset, segment.duration / 2.0)
        seek_time = segment.start_time + offset

        ffmpeg = _check_tool("ffmpeg")
        cmd = [
            ffmpeg, "-y",
            "-ss", str(seek_time),
            "-i", str(source),
            "-vframes", "1",
            "-q:v", "2",
            str(thumb_path),
        ]

        try:
            _run_ffmpeg_split(cmd, timeout=30)
        except SplitError:
            self.logger.warning(
                "Failed to generate thumbnail for segment %d", index + 1,
                exc_info=True,
            )
            return None

        return thumb_path if thumb_path.exists() else None

    # ------------------------------------------------------------------
    # Private: helpers
    # ------------------------------------------------------------------

    def _validate_path(self, path: Path) -> None:
        """Raise :class:`SplitError` if *path* is not a valid video file."""
        if not path.exists():
            raise SplitError(
                f"File not found: {path}",
                path=str(path),
            )
        if not path.is_file():
            raise SplitError(
                f"Not a file: {path}",
                path=str(path),
            )
        if path.suffix.lower() not in _VIDEO_EXTENSIONS:
            raise SplitError(
                f"Unsupported video format {path.suffix!r}. "
                f"Supported: {sorted(_VIDEO_EXTENSIONS)}",
                path=str(path),
                extension=path.suffix,
            )

    def _build_options(self, **overrides: Any) -> VideoSplitOptions:
        """Create a :class:`VideoSplitOptions` from defaults + overrides.

        Parameters
        ----------
        **overrides:
            Field names and values to override on a copy of
            :attr:`default_options`.

        Returns
        -------
        VideoSplitOptions
        """
        if not overrides:
            return self.default_options

        fields = {
            f.name: getattr(self.default_options, f.name)
            for f in self.default_options.__dataclass_fields__.values()
            if f.name not in ("VALID_CODECS", "VALID_QUALITY_PRESETS", "VALID_SUBTITLE_HANDLING")
        }
        fields.update(overrides)

        # Filter out class-level constants that are not constructor params.
        valid_field_names = {
            f.name
            for f in VideoSplitOptions.__dataclass_fields__.values()
            if f.name not in ("VALID_CODECS", "VALID_QUALITY_PRESETS", "VALID_SUBTITLE_HANDLING")
        }
        fields = {k: v for k, v in fields.items() if k in valid_field_names}

        return VideoSplitOptions(**fields)

    def _resolve_extension(
        self, source: Path, options: VideoSplitOptions
    ) -> str:
        """Determine the output file extension.

        When doing a stream copy the input container extension is
        preserved.  Otherwise the extension is chosen based on the
        target codec.

        Parameters
        ----------
        source:
            Source video path.
        options:
            Current split options.

        Returns
        -------
        str
            Extension including the leading dot (e.g. ``".mp4"``).
        """
        if options.codec == "copy":
            return source.suffix
        return _CODEC_CONTAINER_MAP.get(options.codec, source.suffix)

    def _get_video_info(self, path: Path) -> VideoInfo:
        """Retrieve video metadata via ``ffprobe``.

        This is a lightweight helper used internally by convenience
        methods like :meth:`split_by_duration`.

        Parameters
        ----------
        path:
            Path to the video file.

        Returns
        -------
        VideoInfo
        """
        path = Path(path)
        self._validate_path(path)

        data = _run_ffprobe_json([
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(path),
        ])

        video_stream: Dict[str, Any] = {}
        audio_stream: Dict[str, Any] = {}
        for stream in data.get("streams", []):
            codec_type = stream.get("codec_type", "")
            if codec_type == "video" and not video_stream:
                video_stream = stream
            elif codec_type == "audio" and not audio_stream:
                audio_stream = stream

        fmt = data.get("format", {})

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
            format_name=fmt.get("format_name", ""),
            file_size=int(fmt.get("size", 0)),
        )

    @staticmethod
    def _coerce_segment(obj: Any, index: int) -> VideoSegment:
        """Ensure *obj* is a :class:`VideoSegment`, converting if needed.

        If *obj* is a plain dict with ``start_time`` / ``end_time`` keys
        it is promoted to a :class:`VideoSegment`.

        Parameters
        ----------
        obj:
            A :class:`VideoSegment` or dict-like descriptor.
        index:
            Segment index (used for fallback title).

        Returns
        -------
        VideoSegment

        Raises
        ------
        SplitError
            If *obj* cannot be interpreted as a segment.
        """
        if isinstance(obj, VideoSegment):
            return obj

        if isinstance(obj, dict):
            try:
                return VideoSegment(
                    title=obj.get("title", f"Segment {index + 1}"),
                    start_time=float(obj["start_time"]),
                    end_time=float(obj["end_time"]),
                    detection_method=obj.get("detection_method", "unknown"),
                    confidence=float(obj.get("confidence", 1.0)),
                    metadata=obj.get("metadata", {}),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise SplitError(
                    f"Invalid segment dict at index {index}: {exc}",
                    segment=obj,
                ) from exc

        raise SplitError(
            f"Unsupported segment type {type(obj).__name__!r} at index "
            f"{index}; expected VideoSegment or dict.",
            segment_type=type(obj).__name__,
        )
