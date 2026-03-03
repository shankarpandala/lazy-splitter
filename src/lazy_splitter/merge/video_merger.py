"""Video merger implementation using FFmpeg subprocess calls.

Provides :class:`VideoMerger` which can concatenate video files, add
crossfade transitions between clips, and insert chapter markers at join
points -- all driven by the ``ffmpeg`` / ``ffprobe`` CLI tools.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from lazy_splitter.core.base import BaseMerger
from lazy_splitter.core.exceptions import MergeError
from lazy_splitter.core.models import MergeResult
from lazy_splitter.core.utils import ensure_dir, sanitize_filename


class VideoMerger(BaseMerger):
    """Concatenate, crossfade, and chapter-mark video files via FFmpeg.

    All public methods require **ffmpeg** (and optionally **ffprobe**) to be
    available on ``$PATH``.  If the executables are not found a
    :class:`~lazy_splitter.core.exceptions.MergeError` is raised at call
    time.

    Parameters
    ----------
    ffmpeg_path:
        Explicit path to the ``ffmpeg`` binary.  When ``None`` the binary
        is located via :func:`shutil.which`.
    ffprobe_path:
        Explicit path to the ``ffprobe`` binary.  When ``None`` the binary
        is located via :func:`shutil.which`.
    logger:
        Optional :class:`logging.Logger` instance.
    """

    def __init__(
        self,
        ffmpeg_path: Optional[str] = None,
        ffprobe_path: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        super().__init__(logger=logger)
        self._ffmpeg = ffmpeg_path or shutil.which("ffmpeg")
        self._ffprobe = ffprobe_path or shutil.which("ffprobe")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_ffmpeg(self) -> str:
        """Return the ffmpeg path or raise if not available."""
        if not self._ffmpeg:
            raise MergeError(
                "ffmpeg is required for video merging. "
                "Install it from https://ffmpeg.org/ or via your package manager."
            )
        return self._ffmpeg

    def _require_ffprobe(self) -> str:
        """Return the ffprobe path or raise if not available."""
        if not self._ffprobe:
            raise MergeError(
                "ffprobe is required for this operation. "
                "It is usually bundled with ffmpeg."
            )
        return self._ffprobe

    def _run_ffmpeg(self, args: List[str], description: str = "ffmpeg") -> None:
        """Execute an ffmpeg command and raise on failure.

        Parameters
        ----------
        args:
            Full argument list (including the ``ffmpeg`` binary as the
            first element).
        description:
            Human-readable label used in error messages.
        """
        self.logger.debug("Running: %s", " ".join(args))
        try:
            result = subprocess.run(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        except FileNotFoundError as exc:
            raise MergeError(
                f"{description}: executable not found -- {exc}",
            ) from exc

        if result.returncode != 0:
            stderr_text = result.stderr.decode("utf-8", errors="replace")
            raise MergeError(
                f"{description} failed (exit {result.returncode}): {stderr_text[:500]}",
            )

    def _get_duration(self, video_path: Path) -> float:
        """Return the duration of *video_path* in seconds via ffprobe.

        Parameters
        ----------
        video_path:
            Path to a video file.

        Returns
        -------
        float
            Duration in seconds, or ``0.0`` if probing fails.
        """
        ffprobe = self._require_ffprobe()
        try:
            result = subprocess.run(
                [
                    ffprobe,
                    "-v", "quiet",
                    "-print_format", "json",
                    "-show_format",
                    str(video_path),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if result.returncode == 0:
                info = json.loads(result.stdout)
                return float(info.get("format", {}).get("duration", 0.0))
        except Exception:
            self.logger.warning("Could not probe duration for %s", video_path)
        return 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def merge(
        self,
        paths: Sequence[Path],
        output_path: Path,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        **kwargs: Any,
    ) -> MergeResult:
        """Concatenate multiple video files into one.

        Uses the FFmpeg *concat demuxer* for stream-copy concatenation (no
        re-encoding) when all sources share the same codec/container, or the
        *concat filter* when re-encoding is required.

        Parameters
        ----------
        paths:
            Ordered sequence of video file paths.
        output_path:
            Destination path for the merged video.
        progress_callback:
            Optional callable invoked with ``(current_index, total)`` after
            each file is processed.  Note: because FFmpeg processes all
            files in one invocation the callback is fired once before the
            FFmpeg call and once after it completes.
        **kwargs:
            ``reencode`` (bool, default ``False``) -- force re-encoding
            via the concat filter instead of the concat demuxer.
            ``codec`` (str, default ``"copy"``) -- output video codec when
            re-encoding.  ``audio_codec`` (str, default ``"copy"``) --
            output audio codec when re-encoding.

        Returns
        -------
        MergeResult

        Raises
        ------
        MergeError
            If ffmpeg is missing, inputs are invalid, or encoding fails.
        """
        ffmpeg = self._require_ffmpeg()
        validated = self._validate_inputs(paths)
        output_path = Path(output_path)
        ensure_dir(output_path.parent)

        start_time = time.monotonic()
        total = len(validated)
        reencode = kwargs.get("reencode", False)

        if progress_callback is not None:
            progress_callback(0, total)

        if reencode:
            self._merge_filter(ffmpeg, validated, output_path, **kwargs)
        else:
            self._merge_demuxer(ffmpeg, validated, output_path)

        if progress_callback is not None:
            progress_callback(total, total)

        elapsed = time.monotonic() - start_time
        self.logger.info(
            "Merged %d videos into %s (%.2fs)", total, output_path.name, elapsed,
        )

        return MergeResult(
            output_path=output_path,
            source_paths=list(validated),
            duration_seconds=elapsed,
            metadata={"reencode": reencode},
        )

    def merge_with_crossfade(
        self,
        video_paths: Sequence[Path],
        output_path: Path,
        fade_duration: float = 1.0,
    ) -> MergeResult:
        """Concatenate videos with crossfade transitions between clips.

        Re-encoding is always required for crossfade output.

        Parameters
        ----------
        video_paths:
            Ordered sequence of video file paths (at least two).
        output_path:
            Destination for the merged video.
        fade_duration:
            Duration of each crossfade transition in seconds (default 1.0).

        Returns
        -------
        MergeResult
        """
        ffmpeg = self._require_ffmpeg()
        validated = self._validate_inputs(video_paths)
        output_path = Path(output_path)
        ensure_dir(output_path.parent)

        if len(validated) < 2:
            raise MergeError(
                "At least two video files are required for crossfade merging."
            )

        if fade_duration <= 0:
            raise MergeError("fade_duration must be a positive number.")

        start_time = time.monotonic()

        # Build a complex filter graph for crossfading
        n = len(validated)
        input_args: List[str] = []
        for vp in validated:
            input_args.extend(["-i", str(vp)])

        filter_parts: List[str] = []
        # Label each input
        for i in range(n):
            filter_parts.append(f"[{i}:v]setpts=PTS-STARTPTS[v{i}]")
            filter_parts.append(f"[{i}:a]aresample=async=1[a{i}]")

        # Chain xfade filters pair-wise
        prev_v = "v0"
        prev_a = "a0"
        durations = [self._get_duration(v) for v in validated]

        offset = durations[0] - fade_duration if durations[0] > fade_duration else 0.0

        for i in range(1, n):
            out_v = f"xv{i}"
            out_a = f"xa{i}"
            filter_parts.append(
                f"[{prev_v}][v{i}]xfade=transition=fade:"
                f"duration={fade_duration}:offset={max(0.0, offset)}[{out_v}]"
            )
            filter_parts.append(
                f"[{prev_a}][a{i}]acrossfade=d={fade_duration}[{out_a}]"
            )
            prev_v = out_v
            prev_a = out_a
            # Accumulate offset for the next transition
            if i < n - 1:
                offset = offset + durations[i] - fade_duration

        filter_graph = ";".join(filter_parts)

        cmd = [
            ffmpeg, "-y",
            *input_args,
            "-filter_complex", filter_graph,
            "-map", f"[{prev_v}]",
            "-map", f"[{prev_a}]",
            "-c:v", "libx264",
            "-preset", "medium",
            "-c:a", "aac",
            str(output_path),
        ]

        self._run_ffmpeg(cmd, description="crossfade merge")

        elapsed = time.monotonic() - start_time
        self.logger.info(
            "Merged %d videos with crossfade (%.1fs) into %s (%.2fs)",
            n,
            fade_duration,
            output_path.name,
            elapsed,
        )

        return MergeResult(
            output_path=output_path,
            source_paths=list(validated),
            duration_seconds=elapsed,
            metadata={
                "fade_duration": fade_duration,
                "transition": "crossfade",
            },
        )

    def add_chapter_markers(
        self,
        video_path: Path,
        chapters: Sequence[Dict[str, Any]],
        output_path: Path,
    ) -> MergeResult:
        """Add chapter markers to an existing video file.

        Parameters
        ----------
        video_path:
            Path to the source video.
        chapters:
            Sequence of chapter descriptors, each a dict with keys:

            * ``title`` (str) -- chapter title.
            * ``start`` (float) -- start time in seconds.
            * ``end`` (float, optional) -- end time in seconds.  If omitted
              the chapter extends to the start of the next chapter (or EOF
              for the last chapter).
        output_path:
            Destination for the video with embedded chapters.

        Returns
        -------
        MergeResult
        """
        ffmpeg = self._require_ffmpeg()
        validated = self._validate_inputs([video_path])
        output_path = Path(output_path)
        ensure_dir(output_path.parent)

        start_time = time.monotonic()

        # Build an FFmpeg metadata file
        metadata_lines = [";FFMETADATA1"]
        total_duration = self._get_duration(validated[0])

        for idx, ch in enumerate(chapters):
            ch_start = float(ch.get("start", 0))
            if "end" in ch:
                ch_end = float(ch["end"])
            elif idx + 1 < len(chapters):
                ch_end = float(chapters[idx + 1].get("start", total_duration))
            else:
                ch_end = total_duration

            ch_title = str(ch.get("title", f"Chapter {idx + 1}"))

            # FFmpeg metadata uses millisecond-based TIMEBASE or plain
            # seconds multiplied by 1000 with TIMEBASE=1/1000.
            start_ms = int(ch_start * 1000)
            end_ms = int(ch_end * 1000)

            metadata_lines.extend([
                "",
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                f"START={start_ms}",
                f"END={end_ms}",
                f"title={ch_title}",
            ])

        # Write temporary metadata file
        tmp_fd, tmp_meta_path = tempfile.mkstemp(suffix=".txt", prefix="ffmeta_")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                fh.write("\n".join(metadata_lines) + "\n")

            cmd = [
                ffmpeg, "-y",
                "-i", str(validated[0]),
                "-i", tmp_meta_path,
                "-map_metadata", "1",
                "-c", "copy",
                str(output_path),
            ]
            self._run_ffmpeg(cmd, description="add chapters")
        finally:
            try:
                os.unlink(tmp_meta_path)
            except OSError:
                pass

        elapsed = time.monotonic() - start_time
        self.logger.info(
            "Added %d chapter markers to %s -> %s (%.2fs)",
            len(chapters),
            validated[0].name,
            output_path.name,
            elapsed,
        )

        return MergeResult(
            output_path=output_path,
            source_paths=list(validated),
            duration_seconds=elapsed,
            metadata={
                "chapter_count": len(chapters),
                "chapters": [
                    {"title": ch.get("title", ""), "start": ch.get("start", 0)}
                    for ch in chapters
                ],
            },
        )

    # ------------------------------------------------------------------
    # Private merge strategies
    # ------------------------------------------------------------------

    def _merge_demuxer(
        self,
        ffmpeg: str,
        paths: List[Path],
        output_path: Path,
    ) -> None:
        """Merge using the FFmpeg concat demuxer (stream copy, no re-encode).

        Parameters
        ----------
        ffmpeg:
            Path to the ``ffmpeg`` binary.
        paths:
            Validated list of input video paths.
        output_path:
            Destination for the merged file.
        """
        tmp_fd, concat_file = tempfile.mkstemp(
            suffix=".txt", prefix="concat_",
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                for vp in paths:
                    # Paths must be escaped for the concat demuxer format
                    escaped = str(vp).replace("'", "'\\''")
                    fh.write(f"file '{escaped}'\n")

            cmd = [
                ffmpeg, "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                "-c", "copy",
                str(output_path),
            ]
            self._run_ffmpeg(cmd, description="concat demuxer merge")
        finally:
            try:
                os.unlink(concat_file)
            except OSError:
                pass

    def _merge_filter(
        self,
        ffmpeg: str,
        paths: List[Path],
        output_path: Path,
        **kwargs: Any,
    ) -> None:
        """Merge using the FFmpeg concat filter (requires re-encoding).

        Parameters
        ----------
        ffmpeg:
            Path to the ``ffmpeg`` binary.
        paths:
            Validated list of input video paths.
        output_path:
            Destination for the merged file.
        **kwargs:
            ``codec`` -- video codec (default ``"libx264"``).
            ``audio_codec`` -- audio codec (default ``"aac"``).
        """
        n = len(paths)
        input_args: List[str] = []
        for vp in paths:
            input_args.extend(["-i", str(vp)])

        filter_inputs = "".join(f"[{i}:v:0][{i}:a:0]" for i in range(n))
        filter_graph = f"{filter_inputs}concat=n={n}:v=1:a=1[outv][outa]"

        codec = kwargs.get("codec", "libx264")
        audio_codec = kwargs.get("audio_codec", "aac")

        cmd = [
            ffmpeg, "-y",
            *input_args,
            "-filter_complex", filter_graph,
            "-map", "[outv]",
            "-map", "[outa]",
            "-c:v", codec,
            "-c:a", audio_codec,
            str(output_path),
        ]
        self._run_ffmpeg(cmd, description="concat filter merge")
