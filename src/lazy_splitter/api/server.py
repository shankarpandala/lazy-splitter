"""FastAPI REST server for lazy-splitter.

Provides endpoints for splitting, merging, converting, and previewing files,
plus asynchronous job management and result downloads.

All heavy optional dependencies (FastAPI, uvicorn, python-multipart) are
imported inside :func:`create_app` so that the module can be imported for
inspection even when those packages are absent.

Usage::

    # Programmatic
    from lazy_splitter.api.server import create_app
    app = create_app()

    # CLI
    lazy-splitter serve --port 8000

    # Standalone
    python -m lazy_splitter.api

Python 3.8+ compatible.
"""

import io
import logging
import os
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from threading import Thread
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application version (kept in sync with the package)
# ---------------------------------------------------------------------------

__version__ = "0.2.0"

# Server start time, set when the app is created.
_start_time: float = 0.0


# ========================================================================
# Rate limiting helpers
# ========================================================================

class _RateLimiter:
    """Simple in-memory, per-IP sliding-window rate limiter.

    Parameters:
        max_requests: Maximum number of requests allowed within *window*.
        window: Time window in seconds.
    """

    def __init__(self, max_requests: int = 60, window: int = 60) -> None:
        self.max_requests = max_requests
        self.window = window
        self._hits: Dict[str, List[float]] = {}

    def is_allowed(self, client_ip: str) -> bool:
        """Return ``True`` if the request from *client_ip* should be allowed."""
        now = time.time()
        hits = self._hits.setdefault(client_ip, [])

        # Prune old entries.
        cutoff = now - self.window
        self._hits[client_ip] = hits = [t for t in hits if t > cutoff]

        if len(hits) >= self.max_requests:
            return False

        hits.append(now)
        return True


# ========================================================================
# App factory
# ========================================================================

def create_app(
    api_key: Optional[str] = None,
    rate_limit: int = 60,
    cors_origins: Optional[List[str]] = None,
    redis_url: Optional[str] = None,
) -> Any:
    """Create and configure the FastAPI application.

    Parameters:
        api_key: Optional API key for authentication.  When set, requests
            must include an ``X-API-Key`` header with this value.  Can also be
            set via the ``LAZY_SPLITTER_API_KEY`` environment variable.
        rate_limit: Maximum number of requests per IP per minute (0 to disable).
        cors_origins: Allowed CORS origins.  Defaults to ``["*"]``.
        redis_url: Optional Redis URL for the job store.  Falls back to the
            ``LAZY_SPLITTER_REDIS_URL`` environment variable, or in-memory.

    Returns:
        A configured :class:`fastapi.FastAPI` application instance.

    Raises:
        ImportError: If ``fastapi`` or ``python-multipart`` are not installed.
    """
    # -- Lazy imports --------------------------------------------------------
    try:
        from fastapi import (
            FastAPI,
            File,
            Form,
            Header,
            HTTPException,
            Query,
            Request,
            UploadFile,
        )
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import JSONResponse, StreamingResponse
    except ImportError:
        raise ImportError(
            "FastAPI is required for the REST API.  "
            "Install it with:  pip install fastapi uvicorn python-multipart"
        )

    # Ensure python-multipart is available (needed for file uploads).
    try:
        import multipart  # noqa: F401
    except ImportError:
        try:
            import python_multipart  # noqa: F401
        except ImportError:
            raise ImportError(
                "python-multipart is required for file uploads.  "
                "Install it with:  pip install python-multipart"
            )

    from lazy_splitter.api.models import (
        ConvertRequest,
        ConvertResponse,
        ErrorResponse,
        FileInfo,
        FormatsResponse,
        FormatInfo,
        HealthResponse,
        JobStatus,
        MergeRequest,
        MergeResponse,
        PreviewResponse,
        ChapterInfo,
        SplitRequest,
        SplitResponse,
    )
    from lazy_splitter.api.tasks import (
        get_job_store,
        process_convert,
        process_merge,
        process_split,
        start_cleanup_scheduler,
        stop_cleanup_scheduler,
    )

    # -- Configuration -------------------------------------------------------

    effective_api_key = api_key or os.environ.get("LAZY_SPLITTER_API_KEY")
    effective_redis_url = redis_url or os.environ.get("LAZY_SPLITTER_REDIS_URL")

    if cors_origins is None:
        env_origins = os.environ.get("LAZY_SPLITTER_CORS_ORIGINS")
        cors_origins = env_origins.split(",") if env_origins else ["*"]

    limiter = _RateLimiter(max_requests=rate_limit) if rate_limit > 0 else None

    # Initialise the job store early so all endpoints share the same instance.
    store = get_job_store(redis_url=effective_redis_url)

    # -- FastAPI app ---------------------------------------------------------

    global _start_time
    _start_time = time.time()

    app = FastAPI(
        title="lazy-splitter API",
        description=(
            "REST API for splitting, merging, converting, and previewing "
            "documents, audio, video, and image files."
        ),
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -- Lifecycle events ----------------------------------------------------

    @app.on_event("startup")
    async def _on_startup() -> None:  # type: ignore[misc]
        start_cleanup_scheduler()
        logger.info("lazy-splitter API started (version %s).", __version__)

    @app.on_event("shutdown")
    async def _on_shutdown() -> None:  # type: ignore[misc]
        stop_cleanup_scheduler()
        logger.info("lazy-splitter API shutting down.")

    # -- Middleware: auth & rate limiting -------------------------------------

    @app.middleware("http")
    async def _auth_and_rate_limit(request: Request, call_next: Any) -> Any:
        # Skip middleware for docs and health endpoints.
        path = request.url.path
        if path in ("/docs", "/redoc", "/openapi.json", "/api/v1/health"):
            return await call_next(request)

        # API key check.
        if effective_api_key:
            provided = request.headers.get("x-api-key", "")
            if provided != effective_api_key:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing API key."},
                )

        # Rate limiting.
        if limiter is not None:
            client_ip = request.client.host if request.client else "unknown"
            if not limiter.is_allowed(client_ip):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Try again later."},
                )

        return await call_next(request)

    # -- Helper: save uploaded file ------------------------------------------

    def _save_upload(upload: UploadFile, job_id: str) -> str:
        """Save an uploaded file to a temporary location and return its path."""
        from lazy_splitter.core.utils import get_temp_dir

        upload_dir = get_temp_dir() / "api_uploads" / job_id
        upload_dir.mkdir(parents=True, exist_ok=True)

        filename = upload.filename or "upload"
        dest = upload_dir / filename
        with open(dest, "wb") as f:
            shutil.copyfileobj(upload.file, f)
        return str(dest)

    # ====================================================================
    # Endpoints
    # ====================================================================

    # -- POST /api/v1/split --------------------------------------------------

    @app.post(
        "/api/v1/split",
        response_model=SplitResponse,
        responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
        summary="Split a file into chapters / segments",
        tags=["operations"],
    )
    async def split_file(
        file: UploadFile = File(..., description="The file to split."),
        strategy: str = Form("auto", description="Detection strategy."),
        sensitivity: str = Form("medium", description="Detection sensitivity."),
        pattern: Optional[str] = Form(None, description="Custom regex pattern."),
        password: Optional[str] = Form(None, description="File password."),
        pages: Optional[str] = Form(None, description="Page range expression."),
        output_format: Optional[str] = Form(None, description="Output format override."),
    ) -> SplitResponse:
        """Upload a file and split it into chapters or segments.

        The operation runs asynchronously.  Poll ``GET /api/v1/jobs/{job_id}``
        for status updates.
        """
        job = store.create()
        saved = _save_upload(file, job.job_id)
        job.file_paths = [saved]
        store.update(job)

        options: Dict[str, Any] = {
            "strategy": strategy,
            "sensitivity": sensitivity,
            "pattern": pattern,
            "password": password,
            "pages": pages,
            "output_format": output_format,
        }

        thread = Thread(
            target=process_split,
            args=(job.job_id, saved, options),
            daemon=True,
            name="split-%s" % job.job_id,
        )
        thread.start()

        return SplitResponse(
            job_id=job.job_id,
            status=job.status,
            files=[],
            message="Split job submitted. Poll /api/v1/jobs/%s for progress." % job.job_id,
        )

    # -- POST /api/v1/merge --------------------------------------------------

    @app.post(
        "/api/v1/merge",
        response_model=MergeResponse,
        responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
        summary="Merge multiple files into one",
        tags=["operations"],
    )
    async def merge_files(
        files: List[UploadFile] = File(..., description="Files to merge (order matters)."),
        generate_toc: bool = Form(True, description="Generate table of contents."),
        output_format: Optional[str] = Form(None, description="Output format."),
    ) -> MergeResponse:
        """Upload multiple files and merge them into a single document.

        The operation runs asynchronously.
        """
        if len(files) < 2:
            raise HTTPException(status_code=400, detail="At least two files are required for merging.")

        job = store.create()
        saved_paths: List[str] = []
        for f in files:
            saved_paths.append(_save_upload(f, job.job_id))
        job.file_paths = saved_paths
        store.update(job)

        options: Dict[str, Any] = {
            "generate_toc": generate_toc,
            "output_format": output_format,
        }

        thread = Thread(
            target=process_merge,
            args=(job.job_id, saved_paths, options),
            daemon=True,
            name="merge-%s" % job.job_id,
        )
        thread.start()

        return MergeResponse(
            job_id=job.job_id,
            status=job.status,
            output_file=None,
            message="Merge job submitted. Poll /api/v1/jobs/%s for progress." % job.job_id,
        )

    # -- POST /api/v1/convert ------------------------------------------------

    @app.post(
        "/api/v1/convert",
        response_model=ConvertResponse,
        responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
        summary="Convert a file to another format",
        tags=["operations"],
    )
    async def convert_file(
        file: UploadFile = File(..., description="The file to convert."),
        output_format: str = Form(..., description="Target format (e.g. 'epub', 'png', 'mp3')."),
        quality: Optional[int] = Form(None, description="Quality for lossy encodings."),
        dpi: Optional[int] = Form(None, description="Resolution in DPI."),
    ) -> ConvertResponse:
        """Upload a file and convert it to a different format.

        The operation runs asynchronously.
        """
        job = store.create()
        saved = _save_upload(file, job.job_id)
        job.file_paths = [saved]
        store.update(job)

        options: Dict[str, Any] = {
            "output_format": output_format,
            "quality": quality,
            "dpi": dpi,
        }

        thread = Thread(
            target=process_convert,
            args=(job.job_id, saved, options),
            daemon=True,
            name="convert-%s" % job.job_id,
        )
        thread.start()

        return ConvertResponse(
            job_id=job.job_id,
            status=job.status,
            output_file=None,
            message="Conversion job submitted. Poll /api/v1/jobs/%s for progress." % job.job_id,
        )

    # -- POST /api/v1/preview ------------------------------------------------

    @app.post(
        "/api/v1/preview",
        response_model=PreviewResponse,
        responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
        summary="Preview chapter detection without splitting",
        tags=["operations"],
    )
    async def preview_chapters(
        file: UploadFile = File(..., description="The file to preview."),
        strategy: str = Form("auto", description="Detection strategy."),
        sensitivity: str = Form("medium", description="Detection sensitivity."),
        pattern: Optional[str] = Form(None, description="Custom regex pattern."),
        password: Optional[str] = Form(None, description="File password."),
    ) -> PreviewResponse:
        """Upload a file and preview detected chapters / segments.

        This is a synchronous operation that returns results immediately
        (no background job).
        """
        from lazy_splitter.core.utils import detect_file_type, get_temp_dir

        # Save file temporarily.
        tmp_dir = get_temp_dir() / "api_preview"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        filename = file.filename or "preview_upload"
        tmp_path = tmp_dir / filename
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        try:
            file_type = detect_file_type(tmp_path)

            detector: Any = None
            detect_kwargs: Dict[str, Any] = {}

            if file_type == "pdf":
                from pdf_splitter.detector import ChapterDetector

                # ChapterDetector takes sensitivity in __init__;
                # detect() takes (pdf_path, strategy, bookmark_level).
                detector = ChapterDetector(sensitivity=sensitivity or "medium")
                pdf_strategy = strategy if strategy != "auto" else "hybrid"
                detect_kwargs["strategy"] = pdf_strategy
            elif file_type == "epub":
                from epub_splitter.detector import EpubChapterDetector

                # EpubChapterDetector takes strategy and sensitivity in __init__;
                # detect() takes only (epub_path).
                epub_strategy = strategy if strategy != "auto" else "hybrid"
                detector = EpubChapterDetector(
                    strategy=epub_strategy,
                    sensitivity=sensitivity or "medium",
                )
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Preview not supported for file type: %s" % file_type,
                )

            result = detector.detect(tmp_path, **detect_kwargs)

            chapters: List[ChapterInfo] = []
            for ch in result.chapters:
                info = ChapterInfo(
                    title=getattr(ch, "title", str(ch)),
                    start=getattr(ch, "start_page", getattr(ch, "start_time", getattr(ch, "file_path", 0))),
                    end=getattr(ch, "end_page", getattr(ch, "end_time", 0)),
                    level=getattr(ch, "level", 1),
                    detection_method=getattr(ch, "detection_method", "unknown"),
                    confidence=getattr(ch, "confidence", 1.0),
                )
                chapters.append(info)

            # Different detector result types use different attribute names
            # for the total item count (total_pages, total_files, total_items).
            total_items = getattr(
                result, "total_items",
                getattr(result, "total_pages",
                        getattr(result, "total_files", 0)),
            )

            return PreviewResponse(
                chapters=chapters,
                strategy_used=result.strategy_used,
                total_items=total_items,
            )
        finally:
            # Clean up temporary file.
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    # -- POST /api/v1/info ---------------------------------------------------

    @app.post(
        "/api/v1/info",
        response_model=FileInfo,
        responses={400: {"model": ErrorResponse}},
        summary="Get information about a file",
        tags=["info"],
    )
    async def get_file_info(
        file: UploadFile = File(..., description="The file to inspect."),
    ) -> FileInfo:
        """Upload a file and return metadata about it."""
        from lazy_splitter.core.utils import detect_file_type, get_temp_dir

        tmp_dir = get_temp_dir() / "api_info"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        filename = file.filename or "info_upload"
        tmp_path = tmp_dir / filename
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        try:
            file_size = os.path.getsize(tmp_path)

            try:
                file_type = detect_file_type(tmp_path)
            except Exception:
                file_type = "unknown"

            metadata: Dict[str, Any] = {}

            # Extract additional metadata for known types.
            if file_type == "pdf":
                try:
                    import fitz  # type: ignore[import-untyped]

                    doc = fitz.open(str(tmp_path))
                    metadata["page_count"] = len(doc)
                    pdf_meta = doc.metadata
                    if pdf_meta:
                        for key in ("title", "author", "subject", "creator"):
                            val = pdf_meta.get(key)
                            if val:
                                metadata[key] = val
                    doc.close()
                except ImportError:
                    pass

            return FileInfo(
                filename=filename,
                file_type=file_type,
                size=file_size,
                metadata=metadata,
            )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    # -- GET /api/v1/jobs/{job_id} -------------------------------------------

    @app.get(
        "/api/v1/jobs/{job_id}",
        response_model=JobStatus,
        responses={404: {"model": ErrorResponse}},
        summary="Get job status",
        tags=["jobs"],
    )
    async def get_job_status(job_id: str) -> JobStatus:
        """Retrieve the current status of an asynchronous job."""
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found: %s" % job_id)

        return JobStatus(
            job_id=job.job_id,
            status=job.status,
            progress=job.progress,
            result_url=job.result_url,
            error=job.error,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

    # -- GET /api/v1/jobs/{job_id}/download ----------------------------------

    @app.get(
        "/api/v1/jobs/{job_id}/download",
        summary="Download job results as a ZIP archive",
        tags=["jobs"],
        responses={
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
        },
    )
    async def download_job_results(job_id: str) -> StreamingResponse:
        """Download the output files for a completed job as a ZIP archive.

        If only one file was produced it is returned directly; otherwise
        all output files are bundled into a ZIP.
        """
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found: %s" % job_id)

        if job.status != "completed":
            raise HTTPException(
                status_code=409,
                detail="Job is not completed (current status: %s)." % job.status,
            )

        if not job.result_files:
            raise HTTPException(status_code=404, detail="No output files available.")

        # Single file -- stream it directly.
        if len(job.result_files) == 1:
            fpath = Path(job.result_files[0])
            if not fpath.exists():
                raise HTTPException(status_code=404, detail="Output file no longer available.")

            def _iter_file():  # type: ignore[no-untyped-def]
                with open(fpath, "rb") as fh:
                    while True:
                        chunk = fh.read(65536)
                        if not chunk:
                            break
                        yield chunk

            return StreamingResponse(
                _iter_file(),
                media_type="application/octet-stream",
                headers={
                    "Content-Disposition": "attachment; filename=\"%s\"" % fpath.name,
                },
            )

        # Multiple files -- create an in-memory ZIP.
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for fp_str in job.result_files:
                fp = Path(fp_str)
                if fp.exists():
                    zf.write(fp, fp.name)
        buf.seek(0)

        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={
                "Content-Disposition": "attachment; filename=\"%s.zip\"" % job_id,
            },
        )

    # -- GET /api/v1/health --------------------------------------------------

    @app.get(
        "/api/v1/health",
        response_model=HealthResponse,
        summary="Health check",
        tags=["info"],
    )
    async def health_check() -> HealthResponse:
        """Return the health status and uptime of the server."""
        return HealthResponse(
            status="ok",
            version=__version__,
            uptime=round(time.time() - _start_time, 2),
        )

    # -- GET /api/v1/formats -------------------------------------------------

    @app.get(
        "/api/v1/formats",
        response_model=FormatsResponse,
        summary="List supported formats",
        tags=["info"],
    )
    async def list_formats() -> FormatsResponse:
        """Return all file formats supported by lazy-splitter and their
        available conversion targets.
        """
        from lazy_splitter.convert.models import CONVERSION_MAP

        formats: List[FormatInfo] = []
        for ext, targets in sorted(CONVERSION_MAP.items()):
            formats.append(
                FormatInfo(extension=ext, can_convert_to=sorted(set(targets)))
            )
        return FormatsResponse(formats=formats)

    return app
