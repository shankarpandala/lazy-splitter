"""Image splitting for the lazy-splitter image module.

``ImageSplitter`` takes an image file together with a sequence of
:class:`~lazy_splitter.image.models.ImageFrame` descriptors and writes
each frame / region to its own file on disk.

Pillow (``PIL``) is imported lazily so that the rest of the package can be
loaded even on systems where Pillow is not installed.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from lazy_splitter.core.base import BaseSplitter
from lazy_splitter.core.exceptions import SplitError
from lazy_splitter.core.models import DetectionResult
from lazy_splitter.core.utils import ensure_dir, sanitize_filename
from lazy_splitter.image.models import ImageFrame, ImageSplitOptions

try:
    from PIL import Image as PILImage  # type: ignore[import-untyped]

    _HAS_PIL = True
except ImportError:  # pragma: no cover
    _HAS_PIL = False

# Pillow format strings mapped from common user-facing names.
_FORMAT_MAP: Dict[str, str] = {
    "png": "PNG",
    "jpeg": "JPEG",
    "jpg": "JPEG",
    "webp": "WEBP",
    "tiff": "TIFF",
    "tif": "TIFF",
    "bmp": "BMP",
}

# Extensions that correspond to each Pillow format string.
_EXT_MAP: Dict[str, str] = {
    "PNG": ".png",
    "JPEG": ".jpg",
    "WEBP": ".webp",
    "TIFF": ".tiff",
    "BMP": ".bmp",
}

# Default blank-detection threshold: a frame whose pixel variance is
# below this value is considered blank.
_BLANK_VARIANCE_THRESHOLD = 50.0

# Image extensions this splitter can handle.
_SUPPORTED_EXTENSIONS: List[str] = [
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".tiff", ".tif", ".bmp", ".apng",
]

logger = logging.getLogger(__name__)


def _require_pil() -> None:
    """Raise :class:`SplitError` when Pillow is not available."""
    if not _HAS_PIL:
        raise SplitError(
            "Pillow is required for image splitting but is not installed.  "
            "Install it with:  pip install Pillow"
        )


class ImageSplitter(BaseSplitter):
    """Split an image into individual files based on detected frames.

    The splitter supports several splitting modes:

    * **multi-page** -- extract pages from multi-page TIFF images.
    * **animated** -- extract frames from animated GIF, WebP, or APNG.
    * **grid** -- split an image into an *N* x *M* grid of cells.
    * **regions** -- extract user-defined rectangular regions.
    * **sprite-sheet** -- extract fixed-size sprites from a sprite sheet.

    Additional features:

    * Output format conversion (PNG, JPEG, WebP, TIFF, BMP).
    * Quality, DPI, and colour-space control.
    * EXIF metadata preservation.
    * Thumbnail generation alongside full-size outputs.
    * Blank-frame detection and skipping.
    """

    def __init__(
        self,
        options: Optional[ImageSplitOptions] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        super().__init__(logger=logger)
        self.options = options or ImageSplitOptions()

    # ------------------------------------------------------------------
    # Abstract property: supported_extensions
    # ------------------------------------------------------------------

    @property
    def supported_extensions(self) -> List[str]:
        """File extensions this splitter can handle.

        Returns
        -------
        List[str]
            Extensions including the leading dot, e.g. ``[".png", ".jpg"]``.
        """
        return list(_SUPPORTED_EXTENSIONS)

    # ------------------------------------------------------------------
    # Abstract method: preview
    # ------------------------------------------------------------------

    def preview(
        self,
        input_path: Path,
        **kwargs: Any,
    ) -> DetectionResult:
        """Preview what the splitter would produce without writing files.

        Internally delegates to :class:`ImageDetector` and returns the
        detection result so the caller can inspect the frames before
        proceeding with the actual split.

        Parameters
        ----------
        input_path:
            Path to the source image file.
        **kwargs:
            Forwarded to :meth:`ImageDetector.detect`.  Accepts
            ``strategy`` (default ``"auto"``), ``rows``, ``cols``, etc.

        Returns
        -------
        DetectionResult
            Describing the frames that would be created.

        Raises
        ------
        DetectionError
            If detection fails.
        """
        from lazy_splitter.image.detector import ImageDetector

        strategy = kwargs.pop("strategy", "auto")
        detector = ImageDetector(logger=self.logger)
        return detector.detect(input_path, strategy=strategy, **kwargs)

    # ------------------------------------------------------------------
    # Abstract method: split
    # ------------------------------------------------------------------

    def split(
        self,
        input_path: Path,
        chapters: Sequence[Any],
        **kwargs: Any,
    ) -> List[Path]:
        """Split the image at *input_path* according to *chapters*.

        Parameters
        ----------
        input_path:
            Path to the source image.
        chapters:
            Sequence of :class:`ImageFrame` instances that describe which
            frames or regions to extract.
        **kwargs:
            Recognised keys:

            ``output_dir`` (:class:`Path`)
                Directory for the output files.  Defaults to the same
                directory as *input_path*.
            ``progress_callback`` (callable)
                Optional ``(current, total)`` callback invoked after each
                frame is written.

            Plus any field from :class:`ImageSplitOptions`:
            ``output_format``, ``quality``, ``dpi``, ``color_space``,
            ``preserve_exif``, ``generate_thumbnails``,
            ``thumbnail_size``, ``skip_blank``.

        Returns
        -------
        List[Path]
            Paths of the created files.

        Raises
        ------
        SplitError
            If Pillow is missing, the file cannot be opened, or a write
            operation fails.
        """
        _require_pil()
        input_path = Path(input_path)

        if not input_path.is_file():
            raise SplitError(
                f"Image file not found: {input_path}",
                path=str(input_path),
            )

        output_dir = kwargs.pop("output_dir", None)
        progress_callback = kwargs.pop("progress_callback", None)

        opts = self._merge_options(kwargs)
        out_dir = ensure_dir(Path(output_dir) if output_dir else input_path.parent)

        try:
            img = PILImage.open(input_path)
        except Exception as exc:
            raise SplitError(
                f"Cannot open image: {exc}",
                path=str(input_path),
            ) from exc

        # Gather EXIF bytes from the source (used later for preservation).
        exif_bytes = self._extract_exif_bytes(img) if opts.preserve_exif else None

        output_files: List[Path] = []
        total = len(chapters)

        try:
            for current, frame in enumerate(chapters, start=1):
                frame_img = self._extract_frame(img, frame)

                if frame_img is None:
                    if progress_callback is not None:
                        progress_callback(current, total)
                    continue

                # Blank detection.
                if opts.skip_blank and self._is_blank(frame_img):
                    self.logger.debug("Skipping blank frame %d", frame.index)
                    frame_img.close()
                    if progress_callback is not None:
                        progress_callback(current, total)
                    continue

                # Colour-space conversion.
                frame_img = self._apply_color_space(frame_img, opts.color_space)

                # Build the output path.
                out_path = self._output_path(
                    out_dir, input_path.stem, frame, opts.output_format
                )

                # Save full-size image.
                self._save_image(frame_img, out_path, opts, exif_bytes)
                output_files.append(out_path)

                # Thumbnail.
                if opts.generate_thumbnails:
                    thumb_path = self._thumbnail_path(out_path)
                    self._save_thumbnail(
                        frame_img, thumb_path, opts, exif_bytes
                    )
                    output_files.append(thumb_path)

                frame_img.close()

                if progress_callback is not None:
                    progress_callback(current, total)
        except SplitError:
            raise
        except Exception as exc:
            raise SplitError(
                f"Splitting failed: {exc}",
                path=str(input_path),
            ) from exc
        finally:
            img.close()

        return output_files

    # ------------------------------------------------------------------
    # Convenience "shortcut" methods
    # ------------------------------------------------------------------

    def _split_multipage(
        self,
        path: Path,
        frames: Sequence[ImageFrame],
        output_dir: Optional[Path] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[Path]:
        """Split a multi-page TIFF into individual images.

        This is a thin wrapper around :meth:`split` that makes the intent
        explicit in calling code.
        """
        return self.split(
            path,
            chapters=frames,
            output_dir=output_dir,
            progress_callback=progress_callback,
        )

    def _split_animated(
        self,
        path: Path,
        frames: Sequence[ImageFrame],
        output_dir: Optional[Path] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[Path]:
        """Extract frames from an animated GIF, WebP, or APNG.

        Delegates to :meth:`split` -- each frame descriptor's *index*
        field controls which animation frame is sought.
        """
        return self.split(
            path,
            chapters=frames,
            output_dir=output_dir,
            progress_callback=progress_callback,
        )

    def _split_grid(
        self,
        path: Path,
        rows: int = 2,
        cols: int = 2,
        output_dir: Optional[Path] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[Path]:
        """Split an image into an *rows* x *cols* grid of cells.

        Grid-based :class:`ImageFrame` descriptors are built on the fly.
        """
        _require_pil()
        path = Path(path)

        try:
            img = PILImage.open(path)
        except Exception as exc:
            raise SplitError(
                f"Cannot open image: {exc}",
                path=str(path),
            ) from exc

        img_w = img.width
        img_h = img.height
        cell_w = img_w // cols
        cell_h = img_h // rows
        fmt = img.format or ""
        img.close()

        frames: List[ImageFrame] = []
        idx = 0
        for row in range(rows):
            for col in range(cols):
                x = col * cell_w
                y = row * cell_h
                w = img_w - x if col == cols - 1 else cell_w
                h = img_h - y if row == rows - 1 else cell_h
                frames.append(
                    ImageFrame(
                        title=f"Cell R{row + 1}C{col + 1}",
                        index=idx,
                        width=w,
                        height=h,
                        format=fmt,
                        region=(x, y, w, h),
                    )
                )
                idx += 1

        return self.split(
            path,
            chapters=frames,
            output_dir=output_dir,
            progress_callback=progress_callback,
        )

    def _split_regions(
        self,
        path: Path,
        regions: Sequence[Tuple[int, int, int, int]],
        output_dir: Optional[Path] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[Path]:
        """Extract user-defined rectangular regions.

        Parameters
        ----------
        regions:
            Sequence of ``(x, y, width, height)`` tuples.
        """
        frames: List[ImageFrame] = []
        for idx, (x, y, w, h) in enumerate(regions):
            frames.append(
                ImageFrame(
                    title=f"Region {idx + 1}",
                    index=idx,
                    width=w,
                    height=h,
                    region=(x, y, w, h),
                )
            )

        return self.split(
            path,
            chapters=frames,
            output_dir=output_dir,
            progress_callback=progress_callback,
        )

    def _split_sprite_sheet(
        self,
        path: Path,
        sprite_width: int,
        sprite_height: int,
        output_dir: Optional[Path] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[Path]:
        """Extract individual sprites from a sprite sheet.

        The sheet is divided into a grid whose cell size is
        ``sprite_width`` x ``sprite_height``.  Partial cells at the right
        and bottom edges are included.
        """
        _require_pil()
        path = Path(path)

        try:
            img = PILImage.open(path)
        except Exception as exc:
            raise SplitError(
                f"Cannot open image: {exc}",
                path=str(path),
            ) from exc

        img_w, img_h = img.size
        fmt = img.format or ""
        img.close()

        if sprite_width < 1 or sprite_height < 1:
            raise SplitError(
                f"Sprite dimensions must be >= 1, got "
                f"sprite_width={sprite_width}, sprite_height={sprite_height}.",
            )

        frames: List[ImageFrame] = []
        idx = 0
        y = 0
        while y < img_h:
            x = 0
            while x < img_w:
                w = min(sprite_width, img_w - x)
                h = min(sprite_height, img_h - y)
                frames.append(
                    ImageFrame(
                        title=f"Sprite {idx + 1}",
                        index=idx,
                        width=w,
                        height=h,
                        format=fmt,
                        region=(x, y, w, h),
                    )
                )
                idx += 1
                x += sprite_width
            y += sprite_height

        return self.split(
            path,
            chapters=frames,
            output_dir=output_dir,
            progress_callback=progress_callback,
        )

    # ------------------------------------------------------------------
    # Frame extraction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_frame(
        img: "PILImage.Image",
        frame: ImageFrame,
    ) -> "Optional[PILImage.Image]":
        """Seek to the correct frame and optionally crop a region.

        When *frame.region* is set the seek target is frame 0 (the region
        is a spatial crop within a single-frame image).  When *region* is
        ``None`` the frame index controls which page / animation frame is
        extracted.

        Returns a new :class:`PIL.Image.Image` that the caller must
        close, or *None* if the frame cannot be reached.
        """
        # For region-based frames (grid / content / sprites) we always
        # work on the first (and usually only) frame of the image.
        seek_index = 0 if frame.region is not None else frame.index

        try:
            img.seek(seek_index)
        except EOFError:
            logger.warning(
                "Frame index %d is out of range; skipping.", seek_index
            )
            return None

        # Copy so we don't mutate the original.
        result = img.copy()

        # Crop to region if specified.
        if frame.region is not None:
            x, y, w, h = frame.region
            box = (x, y, x + w, y + h)
            result = result.crop(box)

        return result

    # ------------------------------------------------------------------
    # Saving helpers
    # ------------------------------------------------------------------

    def _save_image(
        self,
        img: "PILImage.Image",
        out_path: Path,
        opts: ImageSplitOptions,
        exif_bytes: Optional[bytes],
    ) -> None:
        """Write *img* to *out_path* respecting the split options."""
        pil_format = _FORMAT_MAP.get(opts.output_format.lower(), "PNG")
        save_kwargs = self._build_save_kwargs(pil_format, opts, exif_bytes)

        # Pillow cannot save RGBA to JPEG; convert first.
        img_to_save = self._prepare_for_format(img, pil_format)

        try:
            img_to_save.save(str(out_path), format=pil_format, **save_kwargs)
        except Exception as exc:
            raise SplitError(
                f"Failed to save {out_path}: {exc}",
                path=str(out_path),
            ) from exc

    def _save_thumbnail(
        self,
        img: "PILImage.Image",
        out_path: Path,
        opts: ImageSplitOptions,
        exif_bytes: Optional[bytes],
    ) -> None:
        """Create and save a thumbnail of *img*."""
        thumb = img.copy()
        thumb.thumbnail(opts.thumbnail_size, PILImage.LANCZOS)

        pil_format = _FORMAT_MAP.get(opts.output_format.lower(), "PNG")
        save_kwargs = self._build_save_kwargs(pil_format, opts, exif_bytes)
        thumb_to_save = self._prepare_for_format(thumb, pil_format)

        try:
            thumb_to_save.save(str(out_path), format=pil_format, **save_kwargs)
        except Exception as exc:
            raise SplitError(
                f"Failed to save thumbnail {out_path}: {exc}",
                path=str(out_path),
            ) from exc
        finally:
            thumb.close()

    @staticmethod
    def _build_save_kwargs(
        pil_format: str,
        opts: ImageSplitOptions,
        exif_bytes: Optional[bytes],
    ) -> Dict[str, Any]:
        """Build the keyword arguments dict for ``Image.save``."""
        kwargs: Dict[str, Any] = {}

        if pil_format in ("JPEG", "WEBP"):
            kwargs["quality"] = opts.quality

        if opts.dpi is not None:
            kwargs["dpi"] = opts.dpi

        if exif_bytes and pil_format in ("JPEG", "PNG", "WEBP", "TIFF"):
            kwargs["exif"] = exif_bytes

        return kwargs

    @staticmethod
    def _prepare_for_format(
        img: "PILImage.Image",
        pil_format: str,
    ) -> "PILImage.Image":
        """Ensure *img* is in a mode compatible with *pil_format*."""
        if pil_format == "JPEG" and img.mode in ("RGBA", "LA", "PA", "P"):
            # Flatten alpha onto a white background.
            background = PILImage.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(
                img,
                mask=img.split()[-1] if "A" in img.mode else None,
            )
            return background
        if pil_format == "BMP" and img.mode not in ("RGB", "L", "1", "P"):
            return img.convert("RGB")
        return img

    # ------------------------------------------------------------------
    # Colour-space conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_color_space(
        img: "PILImage.Image",
        color_space: Optional[str],
    ) -> "PILImage.Image":
        """Convert *img* to *color_space* if specified."""
        if color_space is None:
            return img
        try:
            return img.convert(color_space)
        except (ValueError, OSError) as exc:
            logger.warning(
                "Colour-space conversion to %r failed: %s", color_space, exc
            )
            return img

    # ------------------------------------------------------------------
    # EXIF helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_exif_bytes(img: "PILImage.Image") -> Optional[bytes]:
        """Extract raw EXIF bytes from *img* if present."""
        # Pillow >= 6.0 exposes ``getexif()`` which returns an
        # ``Exif`` object that can be serialised with ``tobytes()``.
        try:
            exif = img.getexif()
            if exif:
                return exif.tobytes()
        except Exception:
            pass

        # Fallback: some formats store raw EXIF in ``img.info``.
        info_exif = getattr(img, "info", {}).get("exif")
        if isinstance(info_exif, bytes):
            return info_exif

        return None

    # ------------------------------------------------------------------
    # Blank-frame detection
    # ------------------------------------------------------------------

    @staticmethod
    def _is_blank(
        img: "PILImage.Image",
        threshold: float = _BLANK_VARIANCE_THRESHOLD,
    ) -> bool:
        """Return ``True`` when *img* appears to be a solid-colour frame.

        The check converts the image to greyscale, computes the standard
        deviation of pixel values, and compares it against *threshold*.
        A very low standard deviation implies a near-uniform image.
        """
        try:
            from PIL import ImageStat  # type: ignore[import-untyped]

            grey = img.convert("L")
            stat = ImageStat.Stat(grey)
            # stat.stddev is a list (one entry per channel).
            stddev = stat.stddev[0]
            return stddev < threshold
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _output_path(
        out_dir: Path,
        stem: str,
        frame: ImageFrame,
        output_format: str,
    ) -> Path:
        """Build the output file path for a single frame."""
        pil_format = _FORMAT_MAP.get(output_format.lower(), "PNG")
        ext = _EXT_MAP.get(pil_format, ".png")
        safe_title = sanitize_filename(frame.title)
        filename = f"{stem}_{safe_title}{ext}"
        return out_dir / filename

    @staticmethod
    def _thumbnail_path(full_path: Path) -> Path:
        """Derive the thumbnail path from a full-size output path."""
        return full_path.with_name(
            f"{full_path.stem}_thumb{full_path.suffix}"
        )

    # ------------------------------------------------------------------
    # Options merging
    # ------------------------------------------------------------------

    def _merge_options(self, overrides: Dict[str, Any]) -> ImageSplitOptions:
        """Return a copy of ``self.options`` with *overrides* applied."""
        if not overrides:
            return self.options

        import dataclasses as _dc

        field_names = {f.name for f in _dc.fields(self.options)}
        merged = {}
        for name in field_names:
            if name in overrides:
                merged[name] = overrides[name]
            else:
                merged[name] = getattr(self.options, name)
        return ImageSplitOptions(**merged)
