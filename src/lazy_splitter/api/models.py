"""Pydantic request / response models for the lazy-splitter REST API.

All models use a compatibility shim so that the same source works with both
Pydantic v1 (``>=1.10``) and Pydantic v2 (``>=2.0``).  When Pydantic is not
installed the module still imports cleanly -- callers that actually
*instantiate* the models will get a clear :class:`ImportError` at that point.

Python 3.8+ compatible.
"""

from __future__ import annotations

import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Optional Pydantic import with v1/v2 compatibility
# ---------------------------------------------------------------------------

try:
    import pydantic  # noqa: F401

    _PYDANTIC_MAJOR = int(pydantic.VERSION.split(".")[0])
except ImportError:  # pragma: no cover
    pydantic = None  # type: ignore[assignment]
    _PYDANTIC_MAJOR = 0

if _PYDANTIC_MAJOR >= 2:
    from pydantic import BaseModel, Field
elif _PYDANTIC_MAJOR >= 1:
    from pydantic import BaseModel, Field  # type: ignore[assignment]
else:
    # Lightweight stub so the module is importable even without Pydantic.
    class _StubMeta(type):
        """Metaclass that raises on instantiation when Pydantic is missing."""

        def __call__(cls, *args: Any, **kwargs: Any) -> Any:
            raise ImportError(
                "Pydantic is required for the REST API.  "
                "Install it with:  pip install pydantic>=1.10"
            )

    class BaseModel(metaclass=_StubMeta):  # type: ignore[no-redef]
        """Stub BaseModel used when Pydantic is not installed."""

        class Config:
            pass

    def Field(*args: Any, **kwargs: Any) -> Any:  # type: ignore[misc]
        """Stub Field used when Pydantic is not installed."""
        return kwargs.get("default")


# ========================================================================
# Request models
# ========================================================================


class SplitRequest(BaseModel):
    """Parameters for splitting a file into chapters / segments.

    Sent as form fields alongside the uploaded file on ``POST /api/v1/split``.
    """

    strategy: str = Field(
        default="auto",
        description=(
            "Detection strategy: 'auto', 'bookmarks', 'heuristic', "
            "'toc', 'hybrid', 'regex', 'silence', 'scene'."
        ),
    )
    sensitivity: str = Field(
        default="medium",
        description="Detection sensitivity: 'low', 'medium', or 'high'.",
    )
    pattern: Optional[str] = Field(
        default=None,
        description="Custom regex pattern for regex-based splitting.",
    )
    password: Optional[str] = Field(
        default=None,
        description="Password for encrypted / protected files.",
    )
    pages: Optional[str] = Field(
        default=None,
        description=(
            "Page range expression (e.g. '1-5,8,10-12').  "
            "When provided, only the selected pages are split."
        ),
    )
    output_format: Optional[str] = Field(
        default=None,
        description="Optional output format override (e.g. 'pdf', 'epub').",
    )


class MergeRequest(BaseModel):
    """Parameters for merging multiple files into one.

    Sent as form fields alongside uploaded files on ``POST /api/v1/merge``.
    """

    generate_toc: bool = Field(
        default=True,
        description="Generate a table of contents in the merged output.",
    )
    output_format: Optional[str] = Field(
        default=None,
        description=(
            "Output format.  When *None* the format is inferred from the "
            "first uploaded file."
        ),
    )


class ConvertRequest(BaseModel):
    """Parameters for converting a file between formats.

    Sent as form fields alongside the uploaded file on ``POST /api/v1/convert``.
    """

    output_format: str = Field(
        ...,
        description="Target format (e.g. 'epub', 'png', 'mp3').",
    )
    quality: Optional[int] = Field(
        default=None,
        description="Quality for lossy encodings (format-specific, e.g. 1-100).",
    )
    dpi: Optional[int] = Field(
        default=None,
        description="Resolution in DPI for rasterisation.",
    )


# ========================================================================
# Response models
# ========================================================================


class ChapterInfo(BaseModel):
    """A single detected chapter / segment in a preview response."""

    title: str = Field(description="Chapter title or label.")
    start: Any = Field(description="Start position (page number, timestamp, index).")
    end: Any = Field(description="End position (page number, timestamp, index).")
    level: int = Field(default=1, description="Hierarchy depth (1 = top-level).")
    detection_method: str = Field(default="unknown", description="How this chapter was detected.")
    confidence: float = Field(default=1.0, description="Detection confidence in [0, 1].")


class SplitResponse(BaseModel):
    """Response returned after submitting a split job."""

    job_id: str = Field(description="Unique identifier for this job.")
    status: str = Field(description="Job status: 'pending', 'processing', 'completed', 'failed'.")
    files: List[str] = Field(default_factory=list, description="List of output file names.")
    message: str = Field(default="", description="Human-readable status message.")


class MergeResponse(BaseModel):
    """Response returned after submitting a merge job."""

    job_id: str = Field(description="Unique identifier for this job.")
    status: str = Field(description="Job status.")
    output_file: Optional[str] = Field(default=None, description="Merged output file name.")
    message: str = Field(default="", description="Human-readable status message.")


class ConvertResponse(BaseModel):
    """Response returned after submitting a conversion job."""

    job_id: str = Field(description="Unique identifier for this job.")
    status: str = Field(description="Job status.")
    output_file: Optional[str] = Field(default=None, description="Converted output file name.")
    message: str = Field(default="", description="Human-readable status message.")


class PreviewResponse(BaseModel):
    """Response for a chapter / segment preview request."""

    chapters: List[ChapterInfo] = Field(
        default_factory=list,
        description="Detected chapters / segments.",
    )
    strategy_used: str = Field(default="auto", description="Strategy that produced the results.")
    total_items: int = Field(default=0, description="Total items in the source (pages, frames, ...).")


class JobStatus(BaseModel):
    """Current status of an asynchronous job."""

    job_id: str = Field(description="Unique job identifier.")
    status: str = Field(
        default="pending",
        description="One of 'pending', 'processing', 'completed', 'failed'.",
    )
    progress: float = Field(
        default=0.0,
        description="Completion percentage (0-100).",
    )
    result_url: Optional[str] = Field(
        default=None,
        description="URL to download results when completed.",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message when status is 'failed'.",
    )
    created_at: Optional[str] = Field(
        default=None,
        description="ISO-8601 timestamp when the job was created.",
    )
    updated_at: Optional[str] = Field(
        default=None,
        description="ISO-8601 timestamp of the last status update.",
    )


class FileInfo(BaseModel):
    """Information about an uploaded / inspected file."""

    filename: str = Field(description="Original file name.")
    file_type: str = Field(description="Detected file type (e.g. 'pdf', 'epub').")
    size: int = Field(description="File size in bytes.")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional file metadata (page count, duration, etc.).",
    )


class HealthResponse(BaseModel):
    """Health-check response."""

    status: str = Field(default="ok", description="Service health status.")
    version: str = Field(default="0.2.0", description="Application version string.")
    uptime: float = Field(default=0.0, description="Server uptime in seconds.")


class FormatInfo(BaseModel):
    """Information about a single supported format."""

    extension: str = Field(description="File extension without leading dot.")
    can_convert_to: List[str] = Field(
        default_factory=list,
        description="List of extensions this format can be converted to.",
    )


class FormatsResponse(BaseModel):
    """List of supported formats and their conversion targets."""

    formats: List[FormatInfo] = Field(
        default_factory=list,
        description="All supported formats.",
    )


class ErrorResponse(BaseModel):
    """Standard error response body."""

    detail: str = Field(description="Human-readable error description.")
    error_code: Optional[str] = Field(default=None, description="Machine-readable error code.")
