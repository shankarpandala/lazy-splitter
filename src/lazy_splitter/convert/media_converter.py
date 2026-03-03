"""Media format converters (video, audio, image).

Provides :class:`MediaConverter` with methods for converting between media
formats.  External tools and libraries (FFmpeg via subprocess, pydub, Pillow)
are imported lazily so the module can always be loaded even when optional
dependencies are not installed.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lazy_splitter.core.base import BaseConverter
from lazy_splitter.core.exceptions import ConversionError
from lazy_splitter.core.models import ConversionResult
from lazy_splitter.core.utils import ensure_dir

# ---------------------------------------------------------------------------
# Optional dependency imports
# ---------------------------------------------------------------------------

try:
    from PIL import Image as _PILImage  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    _PILImage = None  # type: ignore[assignment]

try:
    from pydub import AudioSegment as _PydubSegment  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    _PydubSegment = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Format sets for classification
# ---------------------------------------------------------------------------

_VIDEO_EXTENSIONS = frozenset({
    "mp4", "mkv", "avi", "webm", "mov", "wmv", "flv", "ts", "m4v",
})

_AUDIO_EXTENSIONS = frozenset({
    "mp3", "wav", "flac", "ogg", "aac", "m4a", "wma", "opus",
})

_IMAGE_EXTENSIONS = frozenset({
    "png", "jpeg", "jpg", "bmp", "tiff", "tif", "webp", "gif",
})


# ---------------------------------------------------------------------------
# Dependency checkers
# ---------------------------------------------------------------------------

def _require_pillow() -> None:
    """Raise :class:`ConversionError` if Pillow is not installed."""
    if _PILImage is None:
        raise ConversionError(
            "Pillow is required for image conversions. "
            "Install it with: pip install Pillow"
        )


def _require_pydub() -> None:
    """Raise :class:`ConversionError` if pydub is not installed."""
    if _PydubSegment is None:
        raise ConversionError(
            "pydub is required for audio conversions. "
            "Install it with: pip install pydub"
        )


def _require_ffmpeg() -> None:
    """Raise :class:`ConversionError` if the ``ffmpeg`` binary is not on PATH."""
    if shutil.which("ffmpeg") is None:
        raise ConversionError(
            "FFmpeg is required for video conversions but was not found on PATH. "
            "Install FFmpeg from https://ffmpeg.org/ or via your package manager."
        )


def _run_ffmpeg(args: List[str], description: str = "FFmpeg") -> None:
    """Run an FFmpeg subprocess and raise on failure.

    Parameters
    ----------
    args:
        Full argument list (starting with ``"ffmpeg"``).
    description:
        Human-readable label for error messages.

    Raises
    ------
    ConversionError
        If the subprocess exits with a non-zero return code.
    """
    logger.debug("Running: %s", " ".join(args))
    try:
        result = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError:
        raise ConversionError(
            "FFmpeg binary not found. Is it installed and on PATH?"
        )

    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise ConversionError(
            f"{description} failed (exit code {result.returncode}): {stderr}"
        )


# ---------------------------------------------------------------------------
# MediaConverter
# ---------------------------------------------------------------------------

class MediaConverter(BaseConverter):
    """Converter for media formats (video, audio, image).

    Video and audio conversions delegate to FFmpeg (via subprocess) or
    pydub.  Image conversions use Pillow.  The class satisfies the
    :class:`~lazy_splitter.core.base.BaseConverter` interface via the
    generic :meth:`convert` entry-point.
    """

    # ------------------------------------------------------------------
    # Supported conversion pairs
    # ------------------------------------------------------------------

    @property
    def supported_conversions(self) -> List[Tuple[str, str]]:
        """Return the list of (input_format, output_format) pairs supported.

        This is dynamically built from the format sets so new formats only
        need to be added in one place.
        """
        pairs: List[Tuple[str, str]] = []

        # Video -> video
        for src in _VIDEO_EXTENSIONS:
            for dst in _VIDEO_EXTENSIONS:
                if src != dst:
                    pairs.append((src, dst))
            # Video -> GIF
            pairs.append((src, "gif"))
            # Video -> audio (extract)
            for audio in _AUDIO_EXTENSIONS:
                pairs.append((src, audio))

        # Audio -> audio
        for src in _AUDIO_EXTENSIONS:
            for dst in _AUDIO_EXTENSIONS:
                if src != dst:
                    pairs.append((src, dst))

        # Image -> image
        for src in _IMAGE_EXTENSIONS:
            for dst in _IMAGE_EXTENSIONS:
                if src != dst:
                    pairs.append((src, dst))

        return pairs

    # ------------------------------------------------------------------
    # BaseConverter interface
    # ------------------------------------------------------------------

    def convert(
        self,
        input_path: Path,
        output_path: Path,
        output_format: str,
        **kwargs: Any,
    ) -> Path:
        """Auto-dispatch to the appropriate media conversion method.

        Parameters
        ----------
        input_path:
            Source file path.
        output_path:
            Destination file path.
        output_format:
            Target format identifier (e.g. ``"mp4"``, ``"mp3"``, ``"png"``).
        **kwargs:
            Conversion-specific options (``codec``, ``quality``, ``bitrate``,
            ``dpi``, ``fps``, ``width``).

        Returns
        -------
        Path
            Path to the created output file.

        Raises
        ------
        ConversionError
            If the conversion direction is unsupported or an error occurs.
        """
        input_path = Path(input_path)
        output_path = Path(output_path)
        self._validate_input(input_path)

        in_ext = input_path.suffix.lower().lstrip(".")
        out_ext = output_format.lower().lstrip(".")

        # ---- Video source ------------------------------------------------
        if in_ext in _VIDEO_EXTENSIONS:
            if out_ext == "gif":
                return self.video_to_gif(
                    input_path,
                    output_path,
                    fps=kwargs.get("fps", 10),
                    width=kwargs.get("width"),
                )
            if out_ext in _AUDIO_EXTENSIONS:
                return self.extract_audio(
                    input_path,
                    output_path,
                    format=out_ext,
                )
            if out_ext in _VIDEO_EXTENSIONS:
                return self.convert_video(
                    input_path,
                    output_path,
                    codec=kwargs.get("codec"),
                    quality=kwargs.get("quality"),
                )

        # ---- Audio source ------------------------------------------------
        if in_ext in _AUDIO_EXTENSIONS and out_ext in _AUDIO_EXTENSIONS:
            return self.convert_audio(
                input_path,
                output_path,
                format=out_ext,
                bitrate=kwargs.get("bitrate"),
            )

        # ---- Image source ------------------------------------------------
        if in_ext in _IMAGE_EXTENSIONS and out_ext in _IMAGE_EXTENSIONS:
            return self.convert_image(
                input_path,
                output_path,
                format=out_ext,
                quality=kwargs.get("quality"),
                dpi=kwargs.get("dpi"),
            )

        raise ConversionError(
            f"Unsupported media conversion: {in_ext} -> {out_ext}",
            input_format=in_ext,
            output_format=out_ext,
        )

    # ------------------------------------------------------------------
    # Video conversions
    # ------------------------------------------------------------------

    def convert_video(
        self,
        input_path: Path,
        output_path: Path,
        codec: Optional[str] = None,
        quality: Optional[int] = None,
    ) -> Path:
        """Convert a video file to another container/codec.

        Parameters
        ----------
        input_path:
            Path to the source video file.
        output_path:
            Destination path for the converted video.
        codec:
            Video codec name (e.g. ``"libx264"``, ``"libx265"``, ``"vp9"``).
            If *None*, FFmpeg picks a default for the output container.
        quality:
            Constant-rate-factor (CRF) value.  Lower means higher quality.
            Typical range is 18-28 for x264.  If *None*, FFmpeg's default
            is used.

        Returns
        -------
        Path
            Path to the created video file.

        Raises
        ------
        ConversionError
            If FFmpeg is not installed or conversion fails.
        """
        _require_ffmpeg()
        input_path = Path(input_path)
        output_path = Path(output_path)
        ensure_dir(output_path.parent)

        cmd = ["ffmpeg", "-y", "-i", str(input_path)]

        if codec is not None:
            cmd.extend(["-c:v", codec])

        if quality is not None:
            cmd.extend(["-crf", str(quality)])

        cmd.append(str(output_path))
        _run_ffmpeg(cmd, description="Video conversion")

        self.logger.info(
            "Converted video %s -> %s", input_path.name, output_path.name
        )
        return output_path

    def video_to_gif(
        self,
        video_path: Path,
        output_path: Path,
        fps: int = 10,
        width: Optional[int] = None,
    ) -> Path:
        """Convert a video clip to an animated GIF.

        Parameters
        ----------
        video_path:
            Path to the source video file.
        output_path:
            Destination path for the GIF.
        fps:
            Frames per second for the output GIF.
        width:
            Output width in pixels.  Height is scaled proportionally.
            If *None*, the original resolution is used.

        Returns
        -------
        Path
            Path to the created GIF file.

        Raises
        ------
        ConversionError
            If FFmpeg is not installed or conversion fails.
        """
        _require_ffmpeg()
        video_path = Path(video_path)
        output_path = Path(output_path)
        ensure_dir(output_path.parent)

        # Build the filtergraph
        filters = [f"fps={fps}"]
        if width is not None:
            filters.append(f"scale={width}:-1:flags=lanczos")

        # Two-pass palette approach for better quality
        palette_filter = ",".join(filters) + ",palettegen"
        use_filter = ",".join(filters) + " [x]; [x][1:v] paletteuse"

        # Generate palette
        cmd_palette = [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vf", palette_filter,
            "-update", "1",
            str(output_path.parent / "_palette.png"),
        ]
        try:
            _run_ffmpeg(cmd_palette, description="GIF palette generation")

            # Render GIF using palette
            cmd_gif = [
                "ffmpeg", "-y",
                "-i", str(video_path),
                "-i", str(output_path.parent / "_palette.png"),
                "-lavfi", use_filter,
                str(output_path),
            ]
            _run_ffmpeg(cmd_gif, description="GIF rendering")
        finally:
            # Clean up temporary palette file
            palette_file = output_path.parent / "_palette.png"
            if palette_file.exists():
                palette_file.unlink()

        self.logger.info(
            "Converted video to GIF (%d fps, width=%s): %s",
            fps,
            width or "original",
            output_path.name,
        )
        return output_path

    # ------------------------------------------------------------------
    # Audio conversions
    # ------------------------------------------------------------------

    def convert_audio(
        self,
        input_path: Path,
        output_path: Path,
        format: Optional[str] = None,
        bitrate: Optional[str] = None,
    ) -> Path:
        """Convert an audio file to another format.

        Uses pydub (which wraps FFmpeg) for the conversion.

        Parameters
        ----------
        input_path:
            Path to the source audio file.
        output_path:
            Destination path for the converted audio.
        format:
            Target audio format (e.g. ``"mp3"``, ``"wav"``, ``"flac"``).
            If *None*, inferred from *output_path* extension.
        bitrate:
            Target bitrate string (e.g. ``"192k"``, ``"320k"``).
            Only applicable to lossy formats.

        Returns
        -------
        Path
            Path to the created audio file.

        Raises
        ------
        ConversionError
            If pydub is not installed or conversion fails.
        """
        _require_pydub()
        input_path = Path(input_path)
        output_path = Path(output_path)
        ensure_dir(output_path.parent)

        if format is None:
            format = output_path.suffix.lower().lstrip(".")

        # Normalise some format aliases
        fmt = format.lower()
        if fmt == "m4a":
            fmt = "ipod"  # pydub/ffmpeg name for M4A container

        try:
            in_ext = input_path.suffix.lower().lstrip(".")
            audio = _PydubSegment.from_file(  # type: ignore[union-attr]
                str(input_path), format=in_ext
            )
        except Exception as exc:
            raise ConversionError(
                f"Failed to read audio file: {exc}", path=str(input_path)
            ) from exc

        export_kwargs: Dict[str, Any] = {"format": fmt}
        if bitrate is not None:
            export_kwargs["bitrate"] = bitrate

        try:
            audio.export(str(output_path), **export_kwargs)
        except Exception as exc:
            raise ConversionError(
                f"Audio conversion failed: {exc}",
                input_format=in_ext,
                output_format=fmt,
            ) from exc

        self.logger.info(
            "Converted audio %s -> %s (bitrate=%s)",
            input_path.name,
            output_path.name,
            bitrate or "default",
        )
        return output_path

    def extract_audio(
        self,
        video_path: Path,
        output_path: Path,
        format: Optional[str] = None,
    ) -> Path:
        """Extract the audio track from a video file.

        Parameters
        ----------
        video_path:
            Path to the source video file.
        output_path:
            Destination path for the extracted audio.
        format:
            Target audio format (e.g. ``"mp3"``, ``"wav"``).
            If *None*, inferred from *output_path* extension.

        Returns
        -------
        Path
            Path to the created audio file.

        Raises
        ------
        ConversionError
            If FFmpeg is not installed or extraction fails.
        """
        _require_ffmpeg()
        video_path = Path(video_path)
        output_path = Path(output_path)
        ensure_dir(output_path.parent)

        if format is None:
            format = output_path.suffix.lower().lstrip(".")

        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vn",  # Disable video
            "-acodec", self._audio_codec_for_format(format),
            str(output_path),
        ]
        _run_ffmpeg(cmd, description="Audio extraction")

        self.logger.info(
            "Extracted audio from %s -> %s", video_path.name, output_path.name
        )
        return output_path

    # ------------------------------------------------------------------
    # Image conversions
    # ------------------------------------------------------------------

    def convert_image(
        self,
        input_path: Path,
        output_path: Path,
        format: Optional[str] = None,
        quality: Optional[int] = None,
        dpi: Optional[int] = None,
    ) -> Path:
        """Convert an image file to another format using Pillow.

        Parameters
        ----------
        input_path:
            Path to the source image file.
        output_path:
            Destination path for the converted image.
        format:
            Target image format (e.g. ``"png"``, ``"jpeg"``).
            If *None*, inferred from *output_path* extension.
        quality:
            JPEG/WebP quality (1-100).  Ignored for lossless formats.
        dpi:
            Output resolution in dots-per-inch.  Stored in file metadata
            where the format supports it.

        Returns
        -------
        Path
            Path to the created image file.

        Raises
        ------
        ConversionError
            If Pillow is not installed or conversion fails.
        """
        _require_pillow()
        input_path = Path(input_path)
        output_path = Path(output_path)
        ensure_dir(output_path.parent)

        if format is None:
            format = output_path.suffix.lower().lstrip(".")

        # Normalise format names for Pillow
        pil_format = format.upper()
        if pil_format == "JPG":
            pil_format = "JPEG"
        elif pil_format == "TIF":
            pil_format = "TIFF"

        try:
            img = _PILImage.open(str(input_path))  # type: ignore[union-attr]
        except Exception as exc:
            raise ConversionError(
                f"Failed to open image: {exc}", path=str(input_path)
            ) from exc

        # Convert colour mode if necessary (e.g. RGBA -> RGB for JPEG)
        if pil_format == "JPEG" and img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        elif pil_format in ("PNG", "TIFF", "WEBP") and img.mode == "P":
            img = img.convert("RGBA")

        save_kwargs: Dict[str, Any] = {"format": pil_format}
        if quality is not None and pil_format in ("JPEG", "WEBP"):
            save_kwargs["quality"] = quality
        if dpi is not None:
            save_kwargs["dpi"] = (dpi, dpi)

        try:
            img.save(str(output_path), **save_kwargs)
        except Exception as exc:
            raise ConversionError(
                f"Image conversion failed: {exc}",
                input_format=input_path.suffix,
                output_format=format,
            ) from exc
        finally:
            img.close()

        self.logger.info(
            "Converted image %s -> %s (quality=%s, dpi=%s)",
            input_path.name,
            output_path.name,
            quality or "default",
            dpi or "default",
        )
        return output_path

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _audio_codec_for_format(fmt: str) -> str:
        """Return the FFmpeg audio codec name appropriate for *fmt*.

        Parameters
        ----------
        fmt:
            Audio format extension (e.g. ``"mp3"``, ``"wav"``).

        Returns
        -------
        str
            FFmpeg codec string.
        """
        mapping: Dict[str, str] = {
            "mp3": "libmp3lame",
            "wav": "pcm_s16le",
            "flac": "flac",
            "ogg": "libvorbis",
            "aac": "aac",
            "m4a": "aac",
            "opus": "libopus",
            "wma": "wmav2",
        }
        return mapping.get(fmt.lower(), "copy")
