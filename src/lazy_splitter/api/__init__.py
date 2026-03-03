"""REST API and web UI for lazy-splitter.

This package provides a FastAPI-based REST server and a browser-based
interface for splitting, merging, converting, and previewing files.

Quick start::

    # Create the app programmatically
    from lazy_splitter.api import create_app
    app = create_app()

    # Or run from the command line
    python -m lazy_splitter.api --port 8000

All heavy dependencies (FastAPI, uvicorn, Pydantic, python-multipart) are
imported lazily so that this package can be imported for inspection even
when those libraries are not installed.

Exported symbols
----------------
* :func:`create_app`         -- FastAPI application factory.
* :func:`create_web_app`     -- Web UI sub-application factory.
* :func:`run_server`         -- Convenience function to start uvicorn.

Request / response models (Pydantic):
    ``SplitRequest``, ``SplitResponse``, ``MergeRequest``, ``MergeResponse``,
    ``ConvertRequest``, ``ConvertResponse``, ``PreviewResponse``,
    ``JobStatus``, ``FileInfo``, ``HealthResponse``, ``FormatsResponse``,
    ``FormatInfo``, ``ChapterInfo``, ``ErrorResponse``.

Task helpers:
    ``get_job_store``, ``process_split``, ``process_merge``,
    ``process_convert``, ``cleanup_expired_jobs``.
"""

from __future__ import annotations

from typing import Any, List, Optional

# ---------------------------------------------------------------------------
# Re-exports -- models are safe to import eagerly since they only depend on
# Pydantic (or the lightweight stub when Pydantic is absent).
# ---------------------------------------------------------------------------

from lazy_splitter.api.models import (
    ChapterInfo,
    ConvertRequest,
    ConvertResponse,
    ErrorResponse,
    FileInfo,
    FormatInfo,
    FormatsResponse,
    HealthResponse,
    JobStatus,
    MergeRequest,
    MergeResponse,
    PreviewResponse,
    SplitRequest,
    SplitResponse,
)
from lazy_splitter.api.tasks import (
    cleanup_expired_jobs,
    get_job_store,
    process_convert,
    process_merge,
    process_split,
)

__all__ = [
    # App factories
    "create_app",
    "create_web_app",
    "run_server",
    # Models -- requests
    "SplitRequest",
    "MergeRequest",
    "ConvertRequest",
    # Models -- responses
    "SplitResponse",
    "MergeResponse",
    "ConvertResponse",
    "PreviewResponse",
    "JobStatus",
    "FileInfo",
    "HealthResponse",
    "FormatsResponse",
    "FormatInfo",
    "ChapterInfo",
    "ErrorResponse",
    # Tasks
    "get_job_store",
    "process_split",
    "process_merge",
    "process_convert",
    "cleanup_expired_jobs",
]


# ---------------------------------------------------------------------------
# Lazy attribute access for heavy imports (FastAPI / uvicorn)
# ---------------------------------------------------------------------------

def __getattr__(name: str) -> object:
    """Lazily import expensive symbols on first access."""
    if name == "create_app":
        from lazy_splitter.api.server import create_app
        return create_app
    if name == "create_web_app":
        from lazy_splitter.api.web import create_web_app
        return create_web_app
    if name == "run_server":
        # Defined below, but accessed via the module attribute to keep the
        # function in __all__ and importable via ``from lazy_splitter.api import run_server``.
        return _run_server
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


# ---------------------------------------------------------------------------
# Convenience runner
# ---------------------------------------------------------------------------

def _run_server(
    host: str = "0.0.0.0",
    port: int = 8000,
    reload: bool = False,
    workers: int = 1,
    api_key: Optional[str] = None,
    cors_origins: Optional[List[str]] = None,
    log_level: str = "info",
) -> None:
    """Start the lazy-splitter API server using uvicorn.

    This is a convenience wrapper that creates the application, mounts the
    web UI, and launches uvicorn in the current process.

    Parameters:
        host: Bind address.
        port: Bind port.
        reload: Enable auto-reload for development.
        workers: Number of worker processes (ignored when *reload* is True).
        api_key: Optional API key for authentication.
        cors_origins: Allowed CORS origins.
        log_level: Logging level for uvicorn.

    Raises:
        ImportError: If ``uvicorn`` is not installed.
    """
    try:
        import uvicorn
    except ImportError:
        raise ImportError(
            "uvicorn is required to run the server.  "
            "Install it with:  pip install uvicorn"
        )

    from lazy_splitter.api.server import create_app
    from lazy_splitter.api.web import create_web_app

    app = create_app(api_key=api_key, cors_origins=cors_origins)

    # Mount the web UI at the root so it serves HTML pages while the API
    # endpoints remain under /api/v1/.
    web = create_web_app()
    app.mount("/", web)

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=log_level,
        workers=workers if not reload else 1,
    )


# Make run_server available as a direct attribute as well.
run_server = _run_server
