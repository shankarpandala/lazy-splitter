"""Background task processing for the lazy-splitter REST API.

Provides an in-memory job store with optional Redis backend, async task
processors for split / merge / convert operations, and a periodic file
cleanup scheduler.

All heavy optional dependencies (Redis, FastAPI) are imported lazily so
the module remains importable even when those packages are not installed.

Python 3.8+ compatible.
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Job status constants
# ---------------------------------------------------------------------------

STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

# Default time-to-live for completed job artefacts (seconds).
DEFAULT_JOB_TTL: int = 3600  # 1 hour

# Maximum number of jobs held in the in-memory store before old ones are
# evicted.  Has no effect when using the Redis backend.
MAX_IN_MEMORY_JOBS: int = 1000


# ========================================================================
# Job data container
# ========================================================================

class JobData:
    """Mutable container tracking the state of a single background job.

    Attributes:
        job_id: Unique identifier.
        status: One of ``pending``, ``processing``, ``completed``, ``failed``.
        progress: Completion percentage (0-100).
        result_files: Paths to output files once the job finishes.
        result_url: Public download URL set by the server layer.
        error: Error description when ``status == 'failed'``.
        created_at: ISO-8601 creation timestamp.
        updated_at: ISO-8601 timestamp of last status change.
        file_paths: Paths to uploaded input files (cleaned up after the job).
        output_dir: Directory containing the job's output files.
        metadata: Arbitrary extra data.
    """

    __slots__ = (
        "job_id",
        "status",
        "progress",
        "result_files",
        "result_url",
        "error",
        "created_at",
        "updated_at",
        "file_paths",
        "output_dir",
        "metadata",
    )

    def __init__(self, job_id: str) -> None:
        now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        self.job_id: str = job_id
        self.status: str = STATUS_PENDING
        self.progress: float = 0.0
        self.result_files: List[str] = []
        self.result_url: Optional[str] = None
        self.error: Optional[str] = None
        self.created_at: str = now
        self.updated_at: str = now
        self.file_paths: List[str] = []
        self.output_dir: Optional[str] = None
        self.metadata: Dict[str, Any] = {}

    # -- Serialisation -------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serialisable dictionary of the job state."""
        return {
            "job_id": self.job_id,
            "status": self.status,
            "progress": self.progress,
            "result_files": list(self.result_files),
            "result_url": self.result_url,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JobData":
        """Reconstruct a :class:`JobData` from a dictionary."""
        job = cls(data["job_id"])
        job.status = data.get("status", STATUS_PENDING)
        job.progress = float(data.get("progress", 0.0))
        job.result_files = list(data.get("result_files", []))
        job.result_url = data.get("result_url")
        job.error = data.get("error")
        job.created_at = data.get("created_at", job.created_at)
        job.updated_at = data.get("updated_at", job.updated_at)
        job.metadata = dict(data.get("metadata", {}))
        return job

    def _touch(self) -> None:
        """Update the ``updated_at`` timestamp to *now*."""
        self.updated_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"


# ========================================================================
# Abstract job store
# ========================================================================

class BaseJobStore:
    """Abstract interface for job persistence."""

    def create(self, job_id: Optional[str] = None) -> JobData:
        """Create a new job and return it."""
        raise NotImplementedError  # pragma: no cover

    def get(self, job_id: str) -> Optional[JobData]:
        """Return the job with *job_id*, or ``None`` if not found."""
        raise NotImplementedError  # pragma: no cover

    def update(self, job: JobData) -> None:
        """Persist the current state of *job*."""
        raise NotImplementedError  # pragma: no cover

    def delete(self, job_id: str) -> None:
        """Remove the job from the store."""
        raise NotImplementedError  # pragma: no cover

    def list_jobs(self, status: Optional[str] = None) -> List[JobData]:
        """Return all jobs, optionally filtered by *status*."""
        raise NotImplementedError  # pragma: no cover

    def cleanup_expired(self, ttl: int = DEFAULT_JOB_TTL) -> int:
        """Remove completed/failed jobs older than *ttl* seconds.

        Returns the number of jobs removed.
        """
        raise NotImplementedError  # pragma: no cover


# ========================================================================
# In-memory job store (default)
# ========================================================================

class InMemoryJobStore(BaseJobStore):
    """Thread-safe, dictionary-backed job store.

    Suitable for single-process deployments and development.  Jobs are lost
    when the process exits.
    """

    def __init__(self, max_jobs: int = MAX_IN_MEMORY_JOBS) -> None:
        self._jobs: Dict[str, JobData] = {}
        self._lock = threading.Lock()
        self._max_jobs = max_jobs

    def create(self, job_id: Optional[str] = None) -> JobData:
        """Create and store a new :class:`JobData`."""
        if job_id is None:
            job_id = uuid.uuid4().hex[:12]
        job = JobData(job_id)
        with self._lock:
            # Evict oldest completed/failed jobs if at capacity.
            if len(self._jobs) >= self._max_jobs:
                self._evict_oldest()
            self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Optional[JobData]:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job: JobData) -> None:
        job._touch()
        with self._lock:
            self._jobs[job.job_id] = job

    def delete(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)

    def list_jobs(self, status: Optional[str] = None) -> List[JobData]:
        with self._lock:
            jobs = list(self._jobs.values())
        if status is not None:
            jobs = [j for j in jobs if j.status == status]
        return jobs

    def cleanup_expired(self, ttl: int = DEFAULT_JOB_TTL) -> int:
        """Remove finished jobs whose last update is older than *ttl* seconds."""
        cutoff = time.time() - ttl
        removed = 0
        with self._lock:
            to_remove: List[str] = []
            for jid, job in self._jobs.items():
                if job.status not in (STATUS_COMPLETED, STATUS_FAILED):
                    continue
                try:
                    ts_str = job.updated_at.rstrip("Z")
                    updated = datetime.fromisoformat(ts_str)
                    if updated.timestamp() < cutoff:
                        to_remove.append(jid)
                except (ValueError, OSError):
                    pass
            for jid in to_remove:
                job_data = self._jobs.pop(jid, None)
                if job_data is not None:
                    _cleanup_job_files(job_data)
                    removed += 1
        return removed

    # -- Internal helpers ----------------------------------------------------

    def _evict_oldest(self) -> None:
        """Remove the oldest completed/failed job to make room."""
        candidates = [
            j
            for j in self._jobs.values()
            if j.status in (STATUS_COMPLETED, STATUS_FAILED)
        ]
        if not candidates:
            return  # pragma: no cover
        candidates.sort(key=lambda j: j.updated_at)
        oldest = candidates[0]
        self._jobs.pop(oldest.job_id, None)
        _cleanup_job_files(oldest)


# ========================================================================
# Redis-backed job store (optional)
# ========================================================================

class RedisJobStore(BaseJobStore):
    """Job store backed by Redis.

    Requires the ``redis`` package.  Falls back to :class:`InMemoryJobStore`
    if Redis is unavailable.

    Parameters:
        redis_url: Redis connection URL (e.g. ``redis://localhost:6379/0``).
        prefix: Key prefix for all job entries.
        default_ttl: Default expiry in seconds for completed job records.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        prefix: str = "lazy_splitter:job:",
        default_ttl: int = DEFAULT_JOB_TTL,
    ) -> None:
        try:
            import redis as _redis_mod  # type: ignore[import-untyped]

            self._redis = _redis_mod.from_url(redis_url, decode_responses=True)
            self._redis.ping()
        except Exception as exc:
            logger.warning("Redis unavailable (%s); falling back to in-memory store.", exc)
            self._redis = None  # type: ignore[assignment]

        self._prefix = prefix
        self._default_ttl = default_ttl

    @property
    def _available(self) -> bool:
        return self._redis is not None

    def _key(self, job_id: str) -> str:
        return self._prefix + job_id

    def create(self, job_id: Optional[str] = None) -> JobData:
        if job_id is None:
            job_id = uuid.uuid4().hex[:12]
        job = JobData(job_id)
        if self._available:
            import json

            self._redis.set(self._key(job_id), json.dumps(job.to_dict()))
        return job

    def get(self, job_id: str) -> Optional[JobData]:
        if not self._available:
            return None
        import json

        raw = self._redis.get(self._key(job_id))
        if raw is None:
            return None
        return JobData.from_dict(json.loads(raw))

    def update(self, job: JobData) -> None:
        job._touch()
        if self._available:
            import json

            data = json.dumps(job.to_dict())
            if job.status in (STATUS_COMPLETED, STATUS_FAILED):
                self._redis.setex(self._key(job.job_id), self._default_ttl, data)
            else:
                self._redis.set(self._key(job.job_id), data)

    def delete(self, job_id: str) -> None:
        if self._available:
            self._redis.delete(self._key(job_id))

    def list_jobs(self, status: Optional[str] = None) -> List[JobData]:
        if not self._available:
            return []
        import json

        keys = self._redis.keys(self._prefix + "*")
        jobs: List[JobData] = []
        for key in keys:
            raw = self._redis.get(key)
            if raw:
                job = JobData.from_dict(json.loads(raw))
                if status is None or job.status == status:
                    jobs.append(job)
        return jobs

    def cleanup_expired(self, ttl: int = DEFAULT_JOB_TTL) -> int:
        # Redis handles expiry via SETEX; this is a no-op for the Redis backend.
        return 0


# ========================================================================
# Job store factory
# ========================================================================

# Module-level singleton. Initialised lazily via :func:`get_job_store`.
_job_store: Optional[BaseJobStore] = None
_store_lock = threading.Lock()


def get_job_store(redis_url: Optional[str] = None) -> BaseJobStore:
    """Return the global job store singleton.

    On first call the store is created:

    * If *redis_url* is provided (or the ``LAZY_SPLITTER_REDIS_URL``
      environment variable is set) a :class:`RedisJobStore` is attempted.
    * Otherwise an :class:`InMemoryJobStore` is used.

    Returns:
        The active :class:`BaseJobStore`.
    """
    global _job_store
    if _job_store is not None:
        return _job_store

    with _store_lock:
        # Double-check inside the lock.
        if _job_store is not None:
            return _job_store

        url = redis_url or os.environ.get("LAZY_SPLITTER_REDIS_URL")
        if url:
            store = RedisJobStore(redis_url=url)
            if store._available:
                _job_store = store
                logger.info("Using Redis job store at %s", url)
                return _job_store
            logger.info("Redis not reachable; using in-memory job store.")

        _job_store = InMemoryJobStore()
        return _job_store


def reset_job_store() -> None:
    """Reset the global job store singleton (useful in tests)."""
    global _job_store
    with _store_lock:
        _job_store = None


# ========================================================================
# Task processors
# ========================================================================

def _get_output_dir(job: JobData) -> Path:
    """Ensure and return the output directory for a job."""
    from lazy_splitter.core.utils import get_temp_dir

    out = get_temp_dir() / "api_jobs" / job.job_id
    out.mkdir(parents=True, exist_ok=True)
    job.output_dir = str(out)
    return out


def process_split(
    job_id: str,
    file_path: str,
    options: Dict[str, Any],
) -> None:
    """Process a split request in the background.

    Parameters:
        job_id: Unique job identifier.
        file_path: Path to the uploaded file on disk.
        options: Split options (strategy, sensitivity, pattern, password, pages,
            output_format).
    """
    store = get_job_store()
    job = store.get(job_id)
    if job is None:
        logger.error("Job %s not found in store.", job_id)
        return

    job.status = STATUS_PROCESSING
    job.progress = 5.0
    store.update(job)

    try:
        input_path = Path(file_path)
        output_dir = _get_output_dir(job)

        strategy = options.get("strategy", "auto")
        sensitivity = options.get("sensitivity", "medium")
        pattern = options.get("pattern")
        password = options.get("password")
        pages = options.get("pages")

        # Detect file type and load appropriate splitter.
        from lazy_splitter.core.utils import detect_file_type

        file_type = detect_file_type(input_path)
        job.progress = 10.0
        store.update(job)

        splitter: Any = None
        detector: Any = None

        if file_type == "pdf":
            from pdf_splitter.splitter import PDFSplitter
            from pdf_splitter.detector import ChapterDetector

            # ChapterDetector accepts sensitivity in the constructor.
            splitter = PDFSplitter(output_dir=output_dir)
            detector = ChapterDetector(sensitivity=sensitivity)
        elif file_type == "epub":
            from epub_splitter.splitter import EpubSplitter as EPUBSplitter
            from epub_splitter.detector import EpubChapterDetector as EPUBChapterDetector

            # EpubChapterDetector accepts strategy and sensitivity in the
            # constructor; its detect() method takes only the file path.
            epub_strategy = strategy if strategy != "auto" else "hybrid"
            splitter = EPUBSplitter(output_dir=output_dir)
            detector = EPUBChapterDetector(
                strategy=epub_strategy,
                sensitivity=sensitivity,
            )
        else:
            job.status = STATUS_FAILED
            job.error = "Unsupported file type for splitting: %s" % file_type
            store.update(job)
            return

        job.progress = 20.0
        store.update(job)

        # Detection phase.
        # The PDF detector.detect() signature is (pdf_path, strategy, bookmark_level).
        # The EPUB detector.detect() signature is (epub_path) -- strategy is set in __init__.
        detect_kwargs: Dict[str, Any] = {}
        if file_type == "pdf":
            detect_kwargs["strategy"] = strategy if strategy != "auto" else "hybrid"
            if password:
                detect_kwargs["password"] = password

        result = detector.detect(input_path, **detect_kwargs)
        job.progress = 50.0
        store.update(job)

        if not result.chapters:
            job.status = STATUS_FAILED
            job.error = "No chapters detected in the file."
            store.update(job)
            return

        # Split phase.
        created_files = splitter.split(input_path, result.chapters)
        job.progress = 90.0
        store.update(job)

        job.result_files = [str(f) for f in created_files]
        job.status = STATUS_COMPLETED
        job.progress = 100.0
        job.result_url = "/api/v1/jobs/%s/download" % job_id
        store.update(job)

    except Exception as exc:
        logger.exception("Split job %s failed.", job_id)
        job.status = STATUS_FAILED
        job.error = str(exc)
        store.update(job)


def process_merge(
    job_id: str,
    file_paths: List[str],
    options: Dict[str, Any],
) -> None:
    """Process a merge request in the background.

    Parameters:
        job_id: Unique job identifier.
        file_paths: Paths to the uploaded files on disk.
        options: Merge options (generate_toc, output_format).
    """
    store = get_job_store()
    job = store.get(job_id)
    if job is None:
        logger.error("Job %s not found in store.", job_id)
        return

    job.status = STATUS_PROCESSING
    job.progress = 5.0
    store.update(job)

    try:
        paths = [Path(fp) for fp in file_paths]
        output_dir = _get_output_dir(job)
        output_format = options.get("output_format")

        # Infer format from first file.
        from lazy_splitter.core.utils import detect_file_type

        file_type = detect_file_type(paths[0])
        fmt = output_format or file_type

        job.progress = 10.0
        store.update(job)

        # Choose merger.
        merger: Any = None
        output_ext = ".%s" % fmt

        if fmt == "pdf":
            from lazy_splitter.merge.pdf_merger import PDFMerger
            merger = PDFMerger()
            output_ext = ".pdf"
        elif fmt == "epub":
            from lazy_splitter.merge.epub_merger import EpubMerger
            merger = EpubMerger()
            output_ext = ".epub"
        else:
            job.status = STATUS_FAILED
            job.error = "Unsupported format for merging: %s" % fmt
            store.update(job)
            return

        output_path = output_dir / ("merged" + output_ext)
        job.progress = 20.0
        store.update(job)

        generate_toc = options.get("generate_toc", True)
        merge_kwargs: Dict[str, Any] = {}
        if generate_toc is not None:
            merge_kwargs["generate_toc"] = generate_toc

        merger.merge(paths, output_path, **merge_kwargs)
        job.progress = 90.0
        store.update(job)

        job.result_files = [str(output_path)]
        job.status = STATUS_COMPLETED
        job.progress = 100.0
        job.result_url = "/api/v1/jobs/%s/download" % job_id
        store.update(job)

    except Exception as exc:
        logger.exception("Merge job %s failed.", job_id)
        job.status = STATUS_FAILED
        job.error = str(exc)
        store.update(job)


def process_convert(
    job_id: str,
    file_path: str,
    options: Dict[str, Any],
) -> None:
    """Process a conversion request in the background.

    Parameters:
        job_id: Unique job identifier.
        file_path: Path to the uploaded file on disk.
        options: Conversion options (output_format, quality, dpi).
    """
    store = get_job_store()
    job = store.get(job_id)
    if job is None:
        logger.error("Job %s not found in store.", job_id)
        return

    job.status = STATUS_PROCESSING
    job.progress = 5.0
    store.update(job)

    try:
        input_path = Path(file_path)
        output_dir = _get_output_dir(job)
        output_format = options.get("output_format", "")

        if not output_format:
            job.status = STATUS_FAILED
            job.error = "output_format is required for conversion."
            store.update(job)
            return

        from lazy_splitter.core.utils import detect_file_type

        file_type = detect_file_type(input_path)
        job.progress = 10.0
        store.update(job)

        output_ext = ".%s" % output_format.lstrip(".")
        output_path = output_dir / (input_path.stem + output_ext)

        # Build conversion kwargs.
        convert_kwargs: Dict[str, Any] = {}
        quality = options.get("quality")
        dpi = options.get("dpi")
        if quality is not None:
            convert_kwargs["quality"] = quality
        if dpi is not None:
            convert_kwargs["dpi"] = dpi

        job.progress = 20.0
        store.update(job)

        # Attempt to find a suitable converter.
        converted = False

        if file_type == "pdf" and output_format in ("png", "jpeg", "jpg", "tiff", "bmp", "txt"):
            try:
                import fitz  # type: ignore[import-untyped]

                doc = fitz.open(str(input_path))
                if output_format in ("png", "jpeg", "jpg", "tiff", "bmp"):
                    # Render each page as an image.
                    created: List[str] = []
                    total = len(doc)
                    for i, page in enumerate(doc):
                        pix = page.get_pixmap(dpi=dpi or 150)
                        img_path = output_dir / ("%s_page_%03d.%s" % (input_path.stem, i + 1, output_format))
                        pix.save(str(img_path))
                        created.append(str(img_path))
                        job.progress = 20.0 + 70.0 * (i + 1) / total
                        store.update(job)
                    job.result_files = created
                elif output_format in ("txt", "text"):
                    text_parts: List[str] = []
                    for page in doc:
                        text_parts.append(page.get_text())
                    txt_path = output_dir / (input_path.stem + ".txt")
                    txt_path.write_text("\n".join(text_parts), encoding="utf-8")
                    job.result_files = [str(txt_path)]
                doc.close()
                converted = True
            except ImportError:
                pass

        if not converted:
            job.status = STATUS_FAILED
            job.error = (
                "No converter available for %s -> %s. "
                "Required dependencies may not be installed."
                % (file_type, output_format)
            )
            store.update(job)
            return

        job.status = STATUS_COMPLETED
        job.progress = 100.0
        job.result_url = "/api/v1/jobs/%s/download" % job_id
        store.update(job)

    except Exception as exc:
        logger.exception("Convert job %s failed.", job_id)
        job.status = STATUS_FAILED
        job.error = str(exc)
        store.update(job)


# ========================================================================
# File cleanup
# ========================================================================

def _cleanup_job_files(job: JobData) -> None:
    """Remove all files associated with a job from disk."""
    # Clean uploaded input files.
    for fp in job.file_paths:
        try:
            os.unlink(fp)
        except OSError:
            pass

    # Clean output directory.
    if job.output_dir:
        try:
            shutil.rmtree(job.output_dir, ignore_errors=True)
        except OSError:
            pass


def cleanup_expired_jobs(ttl: int = DEFAULT_JOB_TTL) -> int:
    """Remove expired jobs and their associated files from the store.

    Parameters:
        ttl: Time-to-live in seconds for completed/failed jobs.

    Returns:
        Number of jobs cleaned up.
    """
    store = get_job_store()
    return store.cleanup_expired(ttl)


# ========================================================================
# Periodic cleanup scheduler
# ========================================================================

_cleanup_thread: Optional[threading.Thread] = None
_cleanup_stop_event = threading.Event()


def start_cleanup_scheduler(
    interval: int = 600,
    ttl: int = DEFAULT_JOB_TTL,
) -> None:
    """Start a background thread that periodically cleans up expired jobs.

    Parameters:
        interval: Seconds between cleanup runs (default: 10 minutes).
        ttl: Time-to-live for completed/failed jobs.
    """
    global _cleanup_thread

    if _cleanup_thread is not None and _cleanup_thread.is_alive():
        return  # Already running.

    _cleanup_stop_event.clear()

    def _run() -> None:
        while not _cleanup_stop_event.is_set():
            try:
                removed = cleanup_expired_jobs(ttl)
                if removed:
                    logger.info("Cleaned up %d expired jobs.", removed)
            except Exception:
                logger.exception("Error during job cleanup.")
            _cleanup_stop_event.wait(interval)

    _cleanup_thread = threading.Thread(target=_run, daemon=True, name="lazy-splitter-cleanup")
    _cleanup_thread.start()
    logger.info(
        "Cleanup scheduler started (interval=%ds, ttl=%ds).", interval, ttl
    )


def stop_cleanup_scheduler() -> None:
    """Signal the cleanup scheduler to stop."""
    _cleanup_stop_event.set()
    global _cleanup_thread
    _cleanup_thread = None
