"""Image frame / region detection for the lazy-splitter image module.

``ImageDetector`` analyses an image file and returns a
:class:`~lazy_splitter.core.models.DetectionResult` whose *segments* list
contains :class:`~lazy_splitter.image.models.ImageFrame` instances.

Pillow (``PIL``) is imported lazily so that the rest of the package can be
loaded even on systems where Pillow is not installed.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lazy_splitter.core.base import BaseDetector
from lazy_splitter.core.exceptions import DetectionError
from lazy_splitter.core.models import DetectionResult
from lazy_splitter.image.models import ImageFrame, ImageInfo

try:
    from PIL import Image as PILImage  # type: ignore[import-untyped]
    from PIL import ExifTags  # type: ignore[import-untyped]

    _HAS_PIL = True
except ImportError:  # pragma: no cover
    _HAS_PIL = False

# Formats that may carry multiple pages / frames.
_MULTIPAGE_FORMATS = {"TIFF", "MPO"}
_ANIMATED_FORMATS = {"GIF", "WEBP", "PNG"}

# Valid detection strategies.
_STRATEGIES = ("auto", "frames", "grid", "content")

logger = logging.getLogger(__name__)


def _require_pil() -> None:
    """Raise :class:`DetectionError` when Pillow is not available."""
    if not _HAS_PIL:
        raise DetectionError(
            "Pillow is required for image detection but is not installed.  "
            "Install it with:  pip install Pillow"
        )


class ImageDetector(BaseDetector):
    """Detect logical frames or regions inside an image file.

    Supported strategies
    --------------------
    ``"frames"``
        Extract individual pages from multi-page TIFFs or frames from
        animated GIF / WebP / APNG images.
    ``"grid"``
        Partition the image into an *N* x *M* grid of equally-sized cells.
        Requires the keyword arguments ``rows`` and ``cols``.
    ``"content"``
        Perform simple edge / contrast analysis to locate separate images
        on a scanned page.
    ``"auto"``
        Try ``"frames"`` first; if the image has only a single frame fall
        back to ``"content"``.
    """

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        super().__init__(logger=logger)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(
        self,
        input_path: Path,
        strategy: str = "auto",
        **kwargs: Any,
    ) -> DetectionResult:
        """Detect frames or regions in the image at *input_path*.

        Parameters
        ----------
        input_path:
            Path to an image file readable by Pillow.
        strategy:
            One of ``"auto"``, ``"frames"``, ``"grid"``, or ``"content"``.
        **kwargs:
            Strategy-specific options.  ``"grid"`` accepts ``rows`` and
            ``cols`` (both default to ``2``).

        Returns
        -------
        DetectionResult
            A result whose *segments* are :class:`ImageFrame` instances.

        Raises
        ------
        DetectionError
            If the file cannot be opened, Pillow is missing, or the
            strategy is unknown.
        """
        _require_pil()
        path = Path(input_path)

        if strategy not in _STRATEGIES:
            raise DetectionError(
                f"Unknown detection strategy {strategy!r}.  "
                f"Choose from {_STRATEGIES!r}.",
                strategy=strategy,
            )

        if not path.is_file():
            raise DetectionError(
                f"Image file not found: {path}",
                path=str(path),
            )

        try:
            img = PILImage.open(path)
        except Exception as exc:
            raise DetectionError(
                f"Cannot open image: {exc}",
                path=str(path),
            ) from exc

        # Capture metadata before the finally block closes the image.
        img_format = ""
        img_size = (0, 0)
        n_frames = 1

        try:
            if strategy == "frames":
                frames = self._detect_frames(path, img)
            elif strategy == "grid":
                rows = int(kwargs.get("rows", 2))
                cols = int(kwargs.get("cols", 2))
                frames = self._detect_grid(path, img, rows, cols)
            elif strategy == "content":
                frames = self._detect_content(path, img)
            else:  # auto
                frames = self._detect_auto(path, img)

            img_format = img.format or ""
            img_size = (img.width, img.height)
            n_frames = self._count_frames(img)
        except DetectionError:
            raise
        except Exception as exc:
            raise DetectionError(
                f"Detection failed: {exc}",
                path=str(path),
                strategy=strategy,
            ) from exc
        finally:
            img.close()

        return DetectionResult(
            chapters=frames,
            strategy_used=strategy,
            total_items=n_frames,
            source_path=str(path),
            file_type="image",
            metadata={
                "image_format": img_format,
                "image_size": img_size,
            },
        )

    def get_image_info(self, path: Path) -> ImageInfo:
        """Return summarised metadata for the image at *path*.

        Parameters
        ----------
        path:
            Path to an image file.

        Returns
        -------
        ImageInfo
            Populated metadata dataclass.

        Raises
        ------
        DetectionError
            If Pillow is not installed or the file cannot be opened.
        """
        _require_pil()
        path = Path(path)

        if not path.is_file():
            raise DetectionError(
                f"Image file not found: {path}",
                path=str(path),
            )

        try:
            img = PILImage.open(path)
        except Exception as exc:
            raise DetectionError(
                f"Cannot open image: {exc}",
                path=str(path),
            ) from exc

        try:
            frame_count = self._count_frames(img)
            dpi = self._extract_dpi(img)
            has_exif = self._has_exif(img)
            is_animated = self._is_animated(img)
            file_size = os.path.getsize(path)

            return ImageInfo(
                path=path,
                width=img.width,
                height=img.height,
                format=img.format or "",
                mode=img.mode or "",
                frame_count=frame_count,
                dpi=dpi,
                has_exif=has_exif,
                file_size=file_size,
                is_animated=is_animated,
            )
        finally:
            img.close()

    # ------------------------------------------------------------------
    # Strategy implementations
    # ------------------------------------------------------------------

    def _detect_auto(
        self,
        path: Path,
        img: "PILImage.Image",
    ) -> List[ImageFrame]:
        """Auto-detect: try frames first, fall back to content analysis."""
        fmt = (img.format or "").upper()

        if fmt in _MULTIPAGE_FORMATS or fmt in _ANIMATED_FORMATS:
            frames = self._detect_frames(path, img)
            if len(frames) > 1:
                return frames

        # Single-frame image -- try content-aware detection.
        content_frames = self._detect_content(path, img)
        if content_frames:
            return content_frames

        # Fallback: return the whole image as a single frame.
        return [
            ImageFrame(
                title="Frame 1",
                index=0,
                width=img.width,
                height=img.height,
                format=img.format or "",
            )
        ]

    def _detect_frames(
        self,
        path: Path,
        img: "PILImage.Image",
    ) -> List[ImageFrame]:
        """Detect individual pages / animation frames.

        Handles multi-page TIFF, animated GIF, animated WebP, and APNG.
        """
        frames: List[ImageFrame] = []
        fmt = (img.format or "").upper()

        n_frames = self._count_frames(img)
        if n_frames <= 0:
            n_frames = 1

        for idx in range(n_frames):
            try:
                img.seek(idx)
            except EOFError:
                break

            frame_width = img.width
            frame_height = img.height

            metadata: Dict[str, Any] = {}
            if fmt in _ANIMATED_FORMATS:
                # Retrieve frame duration when available.
                info = getattr(img, "info", {})
                duration = info.get("duration")
                if duration is not None:
                    metadata["duration_ms"] = duration

            frames.append(
                ImageFrame(
                    title=f"Frame {idx + 1}",
                    index=idx,
                    width=frame_width,
                    height=frame_height,
                    format=fmt,
                    metadata=metadata,
                )
            )

        # Reset back to the first frame so the caller gets a clean handle.
        try:
            img.seek(0)
        except EOFError:
            pass

        return frames

    def _detect_grid(
        self,
        path: Path,
        img: "PILImage.Image",
        rows: int = 2,
        cols: int = 2,
    ) -> List[ImageFrame]:
        """Partition the image into *rows* x *cols* equal cells."""
        if rows < 1 or cols < 1:
            raise DetectionError(
                f"Grid dimensions must be >= 1, got rows={rows}, cols={cols}.",
                rows=rows,
                cols=cols,
            )

        cell_w = img.width // cols
        cell_h = img.height // rows
        fmt = img.format or ""

        frames: List[ImageFrame] = []
        idx = 0
        for row in range(rows):
            for col in range(cols):
                x = col * cell_w
                y = row * cell_h
                # Last column / row absorbs any remainder pixels.
                w = img.width - x if col == cols - 1 else cell_w
                h = img.height - y if row == rows - 1 else cell_h

                frames.append(
                    ImageFrame(
                        title=f"Cell R{row + 1}C{col + 1}",
                        index=idx,
                        width=w,
                        height=h,
                        format=fmt,
                        region=(x, y, w, h),
                        metadata={"row": row, "col": col},
                    )
                )
                idx += 1

        return frames

    def _detect_content(
        self,
        path: Path,
        img: "PILImage.Image",
    ) -> List[ImageFrame]:
        """Detect separate content regions via simple edge / contrast analysis.

        The algorithm converts the image to greyscale, applies a binary
        threshold to isolate non-background areas, and then walks
        connected horizontal projection bands to locate distinct content
        regions.  This is deliberately kept simple -- heavy-duty
        segmentation should be handled by a dedicated CV backend.
        """
        fmt = img.format or ""

        # Work on a greyscale copy so colour does not confuse us.
        grey = img.convert("L")
        width, height = grey.size
        pixels = grey.load()

        if pixels is None:
            return []

        # ----------------------------------------------------------
        # 1. Compute a row-projection histogram: for each row count
        #    the number of pixels darker than a threshold.
        # ----------------------------------------------------------
        threshold = 200  # pixels brighter than this are "background"
        row_counts: List[int] = []
        for y in range(height):
            count = 0
            for x in range(width):
                if pixels[x, y] < threshold:
                    count += 1
            row_counts.append(count)

        # ----------------------------------------------------------
        # 2. Find contiguous bands of "non-empty" rows.
        # ----------------------------------------------------------
        min_content_pixels = max(1, width // 20)  # at least 5 % of width
        min_band_height = max(1, height // 50)    # ignore tiny slivers

        bands: List[Tuple[int, int]] = []  # (y_start, y_end) inclusive
        band_start: Optional[int] = None

        for y, count in enumerate(row_counts):
            if count >= min_content_pixels:
                if band_start is None:
                    band_start = y
            else:
                if band_start is not None:
                    if y - band_start >= min_band_height:
                        bands.append((band_start, y - 1))
                    band_start = None

        # Close any open band.
        if band_start is not None and height - band_start >= min_band_height:
            bands.append((band_start, height - 1))

        if not bands:
            return []

        # ----------------------------------------------------------
        # 3. For each band, compute the horizontal bounding box.
        # ----------------------------------------------------------
        frames: List[ImageFrame] = []
        for idx, (y_start, y_end) in enumerate(bands):
            x_min = width
            x_max = 0
            for y in range(y_start, y_end + 1):
                for x in range(width):
                    if pixels[x, y] < threshold:
                        if x < x_min:
                            x_min = x
                        if x > x_max:
                            x_max = x

            if x_max < x_min:
                continue

            region_w = x_max - x_min + 1
            region_h = y_end - y_start + 1

            frames.append(
                ImageFrame(
                    title=f"Region {idx + 1}",
                    index=idx,
                    width=region_w,
                    height=region_h,
                    format=fmt,
                    region=(x_min, y_start, region_w, region_h),
                    metadata={"detection": "content"},
                )
            )

        return frames

    # ------------------------------------------------------------------
    # Helper utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _count_frames(img: "PILImage.Image") -> int:
        """Return the number of frames / pages in *img*."""
        try:
            n = getattr(img, "n_frames", 1)
            return int(n) if n else 1
        except Exception:
            return 1

    @staticmethod
    def _is_animated(img: "PILImage.Image") -> bool:
        """Return ``True`` when *img* is an animated image."""
        try:
            return bool(getattr(img, "is_animated", False))
        except Exception:
            return False

    @staticmethod
    def _extract_dpi(img: "PILImage.Image") -> Optional[Tuple[float, float]]:
        """Extract DPI from the image info dict, if present."""
        info = getattr(img, "info", {})
        dpi = info.get("dpi")
        if dpi and isinstance(dpi, (tuple, list)) and len(dpi) >= 2:
            try:
                return (float(dpi[0]), float(dpi[1]))
            except (TypeError, ValueError):
                pass
        return None

    @staticmethod
    def _has_exif(img: "PILImage.Image") -> bool:
        """Return ``True`` when the image carries EXIF metadata."""
        try:
            exif = img.getexif()
            return bool(exif)
        except Exception:
            return False
