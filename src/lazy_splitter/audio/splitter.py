"""Audio splitting engine.

:class:`AudioSplitter` takes a source audio file and a sequence of
:class:`~lazy_splitter.audio.models.AudioSegment` descriptors and writes each
segment as a separate file, optionally re-encoding, normalising, and tagging.

The heavy lifting is done by *pydub* (which in turn delegates to *ffmpeg*).
*mutagen* is used for ID3 / Vorbis / MP4 tag writing.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from lazy_splitter.audio.models import AudioSegment, AudioSplitOptions
from lazy_splitter.core.base import BaseSplitter
from lazy_splitter.core.exceptions import SplitError
from lazy_splitter.core.models import DetectionResult, SplitResult
from lazy_splitter.core.utils import ensure_dir, sanitize_filename

# ---------------------------------------------------------------------------
# Optional dependency imports
# ---------------------------------------------------------------------------

try:
    from pydub import AudioSegment as PydubSegment  # type: ignore[import-untyped]

    _HAS_PYDUB = True
except ImportError:  # pragma: no cover
    _HAS_PYDUB = False

try:
    import mutagen  # type: ignore[import-untyped]
    from mutagen.easyid3 import EasyID3  # type: ignore[import-untyped]
    from mutagen.id3 import ID3  # type: ignore[import-untyped]
    from mutagen.mp4 import MP4  # type: ignore[import-untyped]
    from mutagen.flac import FLAC  # type: ignore[import-untyped]
    from mutagen.oggvorbis import OggVorbis  # type: ignore[import-untyped]

    _HAS_MUTAGEN = True
except ImportError:  # pragma: no cover
    _HAS_MUTAGEN = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------

#: Map from our canonical format names to pydub/ffmpeg format identifiers.
_FORMAT_MAP: Dict[str, str] = {
    "mp3": "mp3",
    "flac": "flac",
    "wav": "wav",
    "ogg": "ogg",
    "aac": "adts",
    "m4a": "ipod",
    "opus": "opus",
}

#: Map from canonical format names to file extensions.
_EXT_MAP: Dict[str, str] = {
    "mp3": ".mp3",
    "flac": ".flac",
    "wav": ".wav",
    "ogg": ".ogg",
    "aac": ".aac",
    "m4a": ".m4a",
    "opus": ".opus",
}

#: Codecs that pydub/ffmpeg needs specified explicitly.
_CODEC_MAP: Dict[str, str] = {
    "aac": "aac",
    "m4a": "aac",
    "opus": "libopus",
    "ogg": "libvorbis",
}


# ---------------------------------------------------------------------------
# AudioSplitter
# ---------------------------------------------------------------------------

class AudioSplitter(BaseSplitter):
    """Split an audio file into multiple segments.

    Parameters
    ----------
    logger:
        Optional logger instance.  Defaults to the module-level logger.
    """

    # -- Abstract property ---------------------------------------------------

    @property
    def supported_extensions(self) -> List[str]:
        """File extensions this splitter can handle.

        Returns
        -------
        list[str]
            Extensions including the leading dot.
        """
        return [
            ".mp3", ".flac", ".wav", ".ogg", ".aac",
            ".m4a", ".m4b", ".mp4", ".opus", ".wma", ".ape",
        ]

    # -- Abstract methods ----------------------------------------------------

    def split(
        self,
        input_path: Path,
        chapters: Sequence[Any],
        **kwargs: Any,
    ) -> List[Path]:
        """Split *input_path* according to *chapters* and write output files.

        This is the :class:`BaseSplitter` contract.  For richer return data
        use :meth:`split_detailed`, which returns a :class:`SplitResult`.

        Parameters
        ----------
        input_path:
            Path to the source audio file.
        chapters:
            Ordered sequence of :class:`AudioSegment` objects describing the
            time ranges to extract.
        **kwargs:
            Accepts ``output_dir``, ``progress_callback``, and all keys
            supported by :class:`AudioSplitOptions` (``output_format``,
            ``bitrate``, ``sample_rate``, ``channels``, ``normalize``,
            ``fade_in_ms``, ``fade_out_ms``).

        Returns
        -------
        list[Path]
            Paths to the created output files.

        Raises
        ------
        SplitError
            If *pydub* is not installed, the source file cannot be read, or
            writing a segment fails.
        """
        result = self.split_detailed(input_path, chapters, **kwargs)
        return result.created_files

    def preview(self, input_path: Path, **kwargs: Any) -> DetectionResult:
        """Preview the segments that would be produced without writing files.

        Internally delegates to :class:`AudioChapterDetector`.

        Parameters
        ----------
        input_path:
            Path to the source audio file.
        **kwargs:
            Forwarded to :meth:`AudioChapterDetector.detect`.  The
            ``strategy`` key selects the detection algorithm (default:
            ``"hybrid"``).

        Returns
        -------
        DetectionResult
        """
        from lazy_splitter.audio.detector import AudioChapterDetector

        detector = AudioChapterDetector(logger=self.logger)
        strategy = kwargs.pop("strategy", "hybrid")
        return detector.detect(Path(input_path), strategy=strategy, **kwargs)

    # -- Extended split with full result ------------------------------------

    def split_detailed(
        self,
        input_path: Path,
        segments: Sequence[Any],
        output_dir: Optional[Path] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        **kwargs: Any,
    ) -> SplitResult:
        """Split *input_path* according to *segments* and return a detailed result.

        Parameters
        ----------
        input_path:
            Path to the source audio file.
        segments:
            Ordered sequence of :class:`AudioSegment` objects describing the
            time ranges to extract.
        output_dir:
            Directory for output files.  Created if it does not exist.
            Defaults to a subdirectory named after the source file.
        progress_callback:
            Optional ``(current_index, total)`` callback invoked after each
            segment is written.
        **kwargs:
            Additional options forwarded to :class:`AudioSplitOptions`.
            Supported keys: ``output_format``, ``bitrate``, ``sample_rate``,
            ``channels``, ``normalize``, ``fade_in_ms``, ``fade_out_ms``.

        Returns
        -------
        SplitResult

        Raises
        ------
        SplitError
            If *pydub* is not installed, the source file cannot be read, or
            writing a segment fails.
        """
        if not _HAS_PYDUB:
            raise SplitError(
                "The 'pydub' package is required for audio splitting. "
                "Install it with: pip install pydub"
            )

        path = Path(input_path)
        if not path.is_file():
            raise SplitError(f"Source file not found: {path}", path=str(path))

        if not segments:
            raise SplitError("No segments to split.", path=str(path))

        # Build options from kwargs
        options = self._build_options(**kwargs)

        # Resolve output directory
        if output_dir is None:
            output_dir = path.parent / f"{path.stem}_split"
        output_dir = ensure_dir(Path(output_dir))

        self.logger.info(
            "Splitting %s into %d segment(s) -> %s [format=%s]",
            path.name,
            len(segments),
            output_dir,
            options.output_format,
        )

        # Load source audio once
        try:
            audio = PydubSegment.from_file(str(path))
        except Exception as exc:
            raise SplitError(
                f"Failed to load audio file: {exc}",
                path=str(path),
            ) from exc

        total_duration_ms = len(audio)
        total = len(segments)
        output_files: List[Path] = []

        for idx, segment in enumerate(segments):
            if not isinstance(segment, AudioSegment):
                raise SplitError(
                    f"Expected AudioSegment, got {type(segment).__name__}",
                    index=idx,
                )

            try:
                out_path = self._split_segment(
                    audio=audio,
                    segment=segment,
                    output_dir=output_dir,
                    index=idx,
                    total=total,
                    total_duration_ms=total_duration_ms,
                    options=options,
                    source_path=path,
                )
                output_files.append(out_path)
            except SplitError:
                raise
            except Exception as exc:
                raise SplitError(
                    f"Failed to write segment {idx + 1}/{total} "
                    f"({segment.title!r}): {exc}",
                    index=idx,
                    segment_title=segment.title,
                ) from exc

            if progress_callback is not None:
                progress_callback(idx + 1, total)

        self.logger.info("Split complete: %d file(s) written", len(output_files))

        return SplitResult(
            created_files=output_files,
            source_path=str(path),
            metadata={
                "output_format": options.output_format,
                "output_dir": str(output_dir),
                "segment_count": len(output_files),
            },
        )

    # ------------------------------------------------------------------
    # Single-segment extraction
    # ------------------------------------------------------------------

    def _split_segment(
        self,
        audio: Any,  # PydubSegment at runtime
        segment: AudioSegment,
        output_dir: Path,
        index: int,
        total: int,
        total_duration_ms: int,
        options: AudioSplitOptions,
        source_path: Path,
    ) -> Path:
        """Extract a single segment from the loaded audio and write it.

        Parameters
        ----------
        audio:
            The full source audio loaded via *pydub*.
        segment:
            Descriptor for the slice to extract.
        output_dir:
            Target directory for the output file.
        index:
            Zero-based index of this segment.
        total:
            Total number of segments (used for track numbering).
        total_duration_ms:
            Duration of the full source audio in milliseconds.
        options:
            Encoding / formatting options.
        source_path:
            Path to the original source file (used in tag metadata).

        Returns
        -------
        Path
            Path to the written output file.
        """
        start_ms = int(segment.start_time * 1000)
        if segment.end_time is not None:
            end_ms = int(segment.end_time * 1000)
        else:
            end_ms = total_duration_ms

        # Clamp to valid range
        start_ms = max(0, min(start_ms, total_duration_ms))
        end_ms = max(start_ms, min(end_ms, total_duration_ms))

        chunk = audio[start_ms:end_ms]

        # -- Normalisation ---------------------------------------------------
        if options.normalize:
            chunk = self._normalize(chunk)

        # -- Fades -----------------------------------------------------------
        if options.fade_in_ms > 0:
            fade_in = min(options.fade_in_ms, len(chunk))
            chunk = chunk.fade_in(fade_in)

        if options.fade_out_ms > 0:
            fade_out = min(options.fade_out_ms, len(chunk))
            chunk = chunk.fade_out(fade_out)

        # -- Channel / sample-rate conversion --------------------------------
        if options.channels is not None and chunk.channels != options.channels:
            if options.channels == 1:
                chunk = chunk.set_channels(1)
            else:
                chunk = chunk.set_channels(options.channels)

        if options.sample_rate is not None and chunk.frame_rate != options.sample_rate:
            chunk = chunk.set_frame_rate(options.sample_rate)

        # -- Build output filename -------------------------------------------
        safe_title = sanitize_filename(segment.title)
        ext = _EXT_MAP.get(options.output_format, f".{options.output_format}")
        filename = f"{index + 1:03d}_{safe_title}{ext}"
        out_path = output_dir / filename

        # -- Export parameters -----------------------------------------------
        export_kwargs: Dict[str, Any] = {
            "format": _FORMAT_MAP.get(options.output_format, options.output_format),
        }

        codec = _CODEC_MAP.get(options.output_format)
        if codec:
            export_kwargs["codec"] = codec

        if options.bitrate and options.output_format not in ("flac", "wav"):
            export_kwargs["bitrate"] = options.bitrate

        # -- Write file ------------------------------------------------------
        self.logger.debug(
            "Writing segment %d/%d: %s (%.1fs)",
            index + 1,
            total,
            out_path.name,
            len(chunk) / 1000.0,
        )

        chunk.export(str(out_path), **export_kwargs)

        # -- Tag the output file ---------------------------------------------
        self._write_tags(
            out_path,
            segment=segment,
            track_number=index + 1,
            total_tracks=total,
            source_path=source_path,
            options=options,
        )

        return out_path

    # ------------------------------------------------------------------
    # Audio normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(chunk: Any, target_dbfs: float = -0.1) -> Any:
        """Normalise *chunk* to *target_dbfs*.

        Parameters
        ----------
        chunk:
            A *pydub* ``AudioSegment``.
        target_dbfs:
            Target peak level in dBFS.

        Returns
        -------
        The normalised ``AudioSegment``.
        """
        current_dbfs = chunk.dBFS
        if current_dbfs == float("-inf"):
            # Silence -- nothing to normalise
            return chunk
        gain = target_dbfs - current_dbfs
        return chunk.apply_gain(gain)

    # ------------------------------------------------------------------
    # Tag writing
    # ------------------------------------------------------------------

    def _write_tags(
        self,
        file_path: Path,
        segment: AudioSegment,
        track_number: int,
        total_tracks: int,
        source_path: Path,
        options: AudioSplitOptions,
    ) -> None:
        """Write ID3 / Vorbis / MP4 tags to the output file.

        This is best-effort: if *mutagen* is unavailable or the format is not
        supported for tagging, the file is left as-is.

        Parameters
        ----------
        file_path:
            Path to the file to tag.
        segment:
            The segment descriptor (title, metadata, etc.).
        track_number:
            Track number (1-based).
        total_tracks:
            Total number of tracks in the split.
        source_path:
            Path to the original source file (for album tagging).
        options:
            Split options (format info).
        """
        if not _HAS_MUTAGEN:
            return

        fmt = options.output_format

        try:
            if fmt == "mp3":
                self._tag_mp3(file_path, segment, track_number, total_tracks, source_path)
            elif fmt in ("m4a", "aac"):
                self._tag_mp4(file_path, segment, track_number, total_tracks, source_path)
            elif fmt == "flac":
                self._tag_flac(file_path, segment, track_number, total_tracks, source_path)
            elif fmt == "ogg":
                self._tag_ogg(file_path, segment, track_number, total_tracks, source_path)
            else:
                self.logger.debug("No tag writer for format %r", fmt)
        except Exception as exc:
            self.logger.warning("Failed to write tags to %s: %s", file_path.name, exc)

    def _tag_mp3(
        self,
        file_path: Path,
        segment: AudioSegment,
        track_number: int,
        total_tracks: int,
        source_path: Path,
    ) -> None:
        """Write ID3v2 tags to an MP3 file."""
        try:
            tags = EasyID3(str(file_path))
        except mutagen.id3.ID3NoHeaderError:
            tags = EasyID3()
            tags.save(str(file_path))
            tags = EasyID3(str(file_path))

        tags["title"] = segment.title
        tags["tracknumber"] = f"{track_number}/{total_tracks}"
        tags["album"] = segment.metadata.get("album", source_path.stem)

        performer = segment.metadata.get("performer")
        if performer:
            tags["artist"] = performer

        tags.save()

    @staticmethod
    def _tag_mp4(
        file_path: Path,
        segment: AudioSegment,
        track_number: int,
        total_tracks: int,
        source_path: Path,
    ) -> None:
        """Write MP4/M4A tags."""
        mp4 = MP4(str(file_path))
        mp4["\xa9nam"] = [segment.title]
        mp4["trkn"] = [(track_number, total_tracks)]
        mp4["\xa9alb"] = [segment.metadata.get("album", source_path.stem)]

        performer = segment.metadata.get("performer")
        if performer:
            mp4["\xa9ART"] = [performer]

        mp4.save()

    @staticmethod
    def _tag_flac(
        file_path: Path,
        segment: AudioSegment,
        track_number: int,
        total_tracks: int,
        source_path: Path,
    ) -> None:
        """Write Vorbis comments to a FLAC file."""
        flac = FLAC(str(file_path))
        flac["TITLE"] = segment.title
        flac["TRACKNUMBER"] = str(track_number)
        flac["TRACKTOTAL"] = str(total_tracks)
        flac["ALBUM"] = segment.metadata.get("album", source_path.stem)

        performer = segment.metadata.get("performer")
        if performer:
            flac["ARTIST"] = performer

        flac.save()

    @staticmethod
    def _tag_ogg(
        file_path: Path,
        segment: AudioSegment,
        track_number: int,
        total_tracks: int,
        source_path: Path,
    ) -> None:
        """Write Vorbis comments to an OGG file."""
        ogg = OggVorbis(str(file_path))
        ogg["TITLE"] = [segment.title]
        ogg["TRACKNUMBER"] = [str(track_number)]
        ogg["TRACKTOTAL"] = [str(total_tracks)]
        ogg["ALBUM"] = [segment.metadata.get("album", source_path.stem)]

        performer = segment.metadata.get("performer")
        if performer:
            ogg["ARTIST"] = [performer]

        ogg.save()

    # ------------------------------------------------------------------
    # Options builder
    # ------------------------------------------------------------------

    @staticmethod
    def _build_options(**kwargs: Any) -> AudioSplitOptions:
        """Construct an :class:`AudioSplitOptions` from keyword arguments.

        Unknown keys are silently ignored so that callers can pass through
        extra ``**kwargs`` without error.
        """
        valid_fields = {f.name for f in AudioSplitOptions.__dataclass_fields__.values()}
        filtered = {k: v for k, v in kwargs.items() if k in valid_fields}
        return AudioSplitOptions(**filtered)
