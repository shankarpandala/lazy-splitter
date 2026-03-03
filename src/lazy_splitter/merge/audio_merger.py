"""Audio merger implementation using pydub.

Provides :class:`AudioMerger` which can concatenate audio files, add
crossfade transitions, and normalise volume levels before merging.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from lazy_splitter.core.base import BaseMerger
from lazy_splitter.core.exceptions import MergeError
from lazy_splitter.core.models import MergeResult
from lazy_splitter.core.utils import ensure_dir, sanitize_filename

try:
    from pydub import AudioSegment  # type: ignore[import-untyped]
    from pydub.effects import normalize as pydub_normalize  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    AudioSegment = None  # type: ignore[assignment,misc]
    pydub_normalize = None  # type: ignore[assignment]

# Map of common file extensions to pydub export format names.
_FORMAT_MAP: Dict[str, str] = {
    ".mp3": "mp3",
    ".wav": "wav",
    ".flac": "flac",
    ".ogg": "ogg",
    ".m4a": "mp4",
    ".aac": "adts",
    ".wma": "wma",
    ".opus": "opus",
}


class AudioMerger(BaseMerger):
    """Concatenate, crossfade, and normalise audio files.

    Requires **pydub** (and an FFmpeg/avconv back-end for non-WAV formats).
    If pydub is not installed a
    :class:`~lazy_splitter.core.exceptions.MergeError` is raised at call
    time.

    Parameters
    ----------
    logger:
        Optional :class:`logging.Logger` instance.
    """

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        super().__init__(logger=logger)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _require_pydub() -> None:
        """Raise if pydub is not available."""
        if AudioSegment is None:
            raise MergeError(
                "pydub is required for audio merging. "
                "Install it with: pip install pydub"
            )

    @staticmethod
    def _detect_format(path: Path) -> str:
        """Infer the pydub format string from a file's extension.

        Parameters
        ----------
        path:
            Audio file path.

        Returns
        -------
        str
            A format identifier understood by :meth:`AudioSegment.from_file`
            (e.g. ``"mp3"``, ``"wav"``).
        """
        ext = path.suffix.lower()
        return _FORMAT_MAP.get(ext, ext.lstrip("."))

    @staticmethod
    def _load(path: Path) -> Any:
        """Load an audio file into an :class:`AudioSegment`.

        Parameters
        ----------
        path:
            Path to the audio file.

        Returns
        -------
        AudioSegment

        Raises
        ------
        MergeError
            If the file cannot be decoded.
        """
        fmt = AudioMerger._detect_format(path)
        try:
            return AudioSegment.from_file(str(path), format=fmt)
        except Exception as exc:
            raise MergeError(
                f"Failed to load audio file: {exc}",
                path=str(path),
            ) from exc

    def _export(
        self,
        segment: Any,
        output_path: Path,
        **kwargs: Any,
    ) -> None:
        """Export an :class:`AudioSegment` to *output_path*.

        Parameters
        ----------
        segment:
            The pydub ``AudioSegment`` to write.
        output_path:
            Destination file.
        **kwargs:
            ``bitrate`` (str) -- e.g. ``"192k"``.  ``tags`` (dict) --
            ID3-style metadata tags.
        """
        fmt = self._detect_format(output_path)
        export_kwargs: Dict[str, Any] = {"format": fmt}

        bitrate = kwargs.get("bitrate")
        if bitrate:
            export_kwargs["bitrate"] = bitrate

        tags = kwargs.get("tags")
        if tags:
            export_kwargs["tags"] = tags

        try:
            segment.export(str(output_path), **export_kwargs)
        except Exception as exc:
            raise MergeError(
                f"Failed to export audio: {exc}",
                path=str(output_path),
            ) from exc

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
        """Concatenate multiple audio files into a single file.

        Parameters
        ----------
        paths:
            Ordered sequence of audio file paths.
        output_path:
            Destination path for the merged audio.
        progress_callback:
            Optional callable invoked with ``(current_index, total)`` after
            each source file is appended.
        **kwargs:
            ``bitrate`` (str) -- output bitrate (e.g. ``"192k"``).
            ``tags`` (dict) -- ID3 / metadata tags for the output file.

        Returns
        -------
        MergeResult

        Raises
        ------
        MergeError
            If pydub is missing, inputs are invalid, or encoding fails.
        """
        self._require_pydub()

        validated = self._validate_inputs(paths)
        output_path = Path(output_path)
        ensure_dir(output_path.parent)

        start_time = time.monotonic()
        total = len(validated)

        combined = AudioSegment.empty()

        for idx, audio_path in enumerate(validated):
            self.logger.debug(
                "Appending %s (%d/%d)", audio_path.name, idx + 1, total,
            )
            segment = self._load(audio_path)
            combined += segment

            if progress_callback is not None:
                progress_callback(idx + 1, total)

        self._export(combined, output_path, **kwargs)

        elapsed = time.monotonic() - start_time
        self.logger.info(
            "Merged %d audio files into %s (%.2fs)", total, output_path.name, elapsed,
        )

        return MergeResult(
            output_path=output_path,
            source_paths=list(validated),
            duration_seconds=elapsed,
            metadata={
                "total_duration_ms": len(combined),
                "sample_rate": combined.frame_rate,
                "channels": combined.channels,
            },
        )

    def merge_with_crossfade(
        self,
        audio_paths: Sequence[Path],
        output_path: Path,
        fade_ms: int = 1000,
        **kwargs: Any,
    ) -> MergeResult:
        """Concatenate audio files with crossfade transitions.

        Parameters
        ----------
        audio_paths:
            Ordered sequence of audio file paths (at least two).
        output_path:
            Destination for the merged audio.
        fade_ms:
            Duration of each crossfade in milliseconds (default 1000).
        **kwargs:
            ``bitrate`` (str) -- output bitrate.

        Returns
        -------
        MergeResult

        Raises
        ------
        MergeError
            If fewer than two files are provided, if the crossfade duration
            exceeds the length of any source file, or if encoding fails.
        """
        self._require_pydub()

        validated = self._validate_inputs(audio_paths)
        output_path = Path(output_path)
        ensure_dir(output_path.parent)

        if len(validated) < 2:
            raise MergeError(
                "At least two audio files are required for crossfade merging."
            )
        if fade_ms <= 0:
            raise MergeError("fade_ms must be a positive integer.")

        start_time = time.monotonic()

        segments = [self._load(p) for p in validated]

        # Validate that no segment is shorter than the fade duration
        for idx, seg in enumerate(segments):
            if len(seg) < fade_ms:
                raise MergeError(
                    f"Audio file {validated[idx].name} is shorter than the "
                    f"crossfade duration ({len(seg)}ms < {fade_ms}ms).",
                    path=str(validated[idx]),
                )

        combined = segments[0]
        for seg in segments[1:]:
            combined = combined.append(seg, crossfade=fade_ms)

        self._export(combined, output_path, **kwargs)

        elapsed = time.monotonic() - start_time
        self.logger.info(
            "Merged %d audio files with %dms crossfade into %s (%.2fs)",
            len(validated),
            fade_ms,
            output_path.name,
            elapsed,
        )

        return MergeResult(
            output_path=output_path,
            source_paths=list(validated),
            duration_seconds=elapsed,
            metadata={
                "total_duration_ms": len(combined),
                "fade_ms": fade_ms,
                "transition": "crossfade",
            },
        )

    def normalize_and_merge(
        self,
        audio_paths: Sequence[Path],
        output_path: Path,
        **kwargs: Any,
    ) -> MergeResult:
        """Normalise volume of each source and then concatenate.

        Each source file is individually normalised to ``-0.1 dBFS`` before
        being appended.  This ensures consistent perceived volume across
        segments that may have been recorded at different levels.

        Parameters
        ----------
        audio_paths:
            Ordered sequence of audio file paths.
        output_path:
            Destination for the merged audio.
        **kwargs:
            ``bitrate`` (str) -- output bitrate.
            ``headroom`` (float) -- dBFS headroom for normalisation
            (default ``0.1``).

        Returns
        -------
        MergeResult
        """
        self._require_pydub()

        if pydub_normalize is None:
            raise MergeError(
                "pydub.effects.normalize is required for volume normalisation."
            )

        validated = self._validate_inputs(audio_paths)
        output_path = Path(output_path)
        ensure_dir(output_path.parent)

        start_time = time.monotonic()
        total = len(validated)
        headroom = float(kwargs.pop("headroom", 0.1))

        combined = AudioSegment.empty()

        for idx, audio_path in enumerate(validated):
            self.logger.debug(
                "Normalising and appending %s (%d/%d)",
                audio_path.name,
                idx + 1,
                total,
            )
            segment = self._load(audio_path)
            segment = pydub_normalize(segment, headroom=headroom)
            combined += segment

        self._export(combined, output_path, **kwargs)

        elapsed = time.monotonic() - start_time
        self.logger.info(
            "Normalised and merged %d audio files into %s (%.2fs)",
            total,
            output_path.name,
            elapsed,
        )

        return MergeResult(
            output_path=output_path,
            source_paths=list(validated),
            duration_seconds=elapsed,
            metadata={
                "total_duration_ms": len(combined),
                "headroom_dbfs": headroom,
                "normalized": True,
            },
        )
