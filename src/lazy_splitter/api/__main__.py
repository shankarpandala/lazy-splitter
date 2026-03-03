"""Allow running the API server as ``python -m lazy_splitter.api``.

Usage::

    python -m lazy_splitter.api
    python -m lazy_splitter.api --port 9000
    python -m lazy_splitter.api --host 127.0.0.1 --port 8080
    python -m lazy_splitter.api --api-key my-secret-key
    python -m lazy_splitter.api --reload   # development auto-reload
    python -m lazy_splitter.api --help

This module is also invoked when the CLI command ``lazy-splitter serve``
is used.

Python 3.8+ compatible.
"""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    """Parse CLI arguments and start the lazy-splitter API server."""
    parser = argparse.ArgumentParser(
        prog="python -m lazy_splitter.api",
        description="Start the lazy-splitter REST API and web UI server.",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Bind address (default: 0.0.0.0).",
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=8000,
        help="Bind port (default: 8000).",
    )
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=1,
        help="Number of worker processes (default: 1).",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        default=False,
        help="Enable auto-reload for development.",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help=(
            "Require this API key in the X-API-Key header.  "
            "Can also be set via the LAZY_SPLITTER_API_KEY env var."
        ),
    )
    parser.add_argument(
        "--cors-origins",
        default=None,
        help="Comma-separated list of allowed CORS origins (default: '*').",
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["debug", "info", "warning", "error", "critical"],
        help="Logging level (default: info).",
    )

    args = parser.parse_args()

    # -- Dependency check ----------------------------------------------------

    try:
        import uvicorn  # noqa: F401
    except ImportError:
        print(
            "The API server requires uvicorn.  Install it with:\n"
            "  pip install uvicorn python-multipart fastapi",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        import fastapi  # noqa: F401
    except ImportError:
        print(
            "The API server requires FastAPI.  Install it with:\n"
            "  pip install fastapi python-multipart",
            file=sys.stderr,
        )
        sys.exit(1)

    # -- Build origins list --------------------------------------------------

    cors_origins = None
    if args.cors_origins:
        cors_origins = [o.strip() for o in args.cors_origins.split(",")]

    # -- Start server --------------------------------------------------------

    from lazy_splitter.api import run_server

    print("Starting lazy-splitter API server on %s:%d" % (args.host, args.port))
    print("  API docs:  http://%s:%d/docs" % (args.host, args.port))
    print("  Web UI:    http://%s:%d/" % (args.host, args.port))
    if args.api_key:
        print("  API key:   required (set via --api-key)")
    print()

    run_server(
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers,
        api_key=args.api_key,
        cors_origins=cors_origins,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
