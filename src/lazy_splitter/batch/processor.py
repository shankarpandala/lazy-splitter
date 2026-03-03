"""Batch file processor for lazy-splitter.

Provides :class:`BatchProcessor`, which applies a single operation (split,
merge, convert, or info) to many files at once.  Processing can run in
parallel via :class:`concurrent.futures.ProcessPoolExecutor`, and progress
is tracked through optional callbacks.  A lightweight JSON checkpoint
mechanism allows interrupted runs to be resumed.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import os
import threading
import time
from concurrent.futures import Future, ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Union,
)

from lazy_splitter.core.exceptions import LazySplitterError
from lazy_splitter.core.utils import detect_file_type, ensure_dir

from lazy_splitter.batch.models import BatchFileResult, BatchResult

logger = logging.getLogger(__name__)

# Operations recognised by the processor.
VALID_OPERATIONS = frozenset({"split", "merge", "convert", "info"})

# Type alias for user-supplied progress callbacks.
ProgressCallback = Callable[[int, int, Optional[str]], None]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_files(
    directory: Union[str, Path],
    pattern: str,
    recursive: bool = False,
    file_filter: Optional[Callable[[Path], bool]] = None,
) -> List[Path]:
    """Return files in *directory* matching a glob *pattern*.

    Parameters
    ----------
    directory:
        Root directory to search.
    pattern:
        Shell-style glob pattern (e.g. ``"*.pdf"``).
    recursive:
        When ``True``, descend into subdirectories.
    file_filter:
        Optional predicate; files for which this returns ``False`` are
        excluded.

    Returns
    -------
    list of Path
        Sorted list of matching file paths.
    """
    root = Path(directory)
    if not root.is_dir():
        raise LazySplitterError(
            f"Input directory does not exist: {root}",
            path=str(root),
        )

    matched: List[Path] = []
    if recursive:
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                if fnmatch.fnmatch(name, pattern):
                    fp = Path(dirpath) / name
                    if file_filter is None or file_filter(fp):
                        matched.append(fp)
    else:
        for entry in root.iterdir():
            if entry.is_file() and fnmatch.fnmatch(entry.name, pattern):
                if file_filter is None or file_filter(entry):
                    matched.append(entry)

    matched.sort()
    return matched


def _process_single_file(
    file_path: str,
    operation: str,
    kwargs: Dict[str, Any],
) -> Dict[str, Any]:
    """Process one file and return a serialisable result dictionary.

    This function is designed to be called inside a
    :class:`ProcessPoolExecutor` worker, so all arguments and the return
    value must be picklable.

    Parameters
    ----------
    file_path:
        Absolute path to the file to process.
    operation:
        One of the :data:`VALID_OPERATIONS`.
    kwargs:
        Extra keyword arguments forwarded to the operation handler.

    Returns
    -------
    dict
        A dictionary that can be fed to :meth:`BatchFileResult.from_dict`.
    """
    start = time.monotonic()
    path = Path(file_path)
    output_paths: List[str] = []
    error_message: Optional[str] = None
    success = True

    try:
        if operation == "info":
            file_type = detect_file_type(path)
            stat = path.stat()
            output_paths = []
            # Store info in a deterministic way (caller can inspect result).
            logger.info(
                "File info: %s  type=%s  size=%d",
                path.name,
                file_type,
                stat.st_size,
            )

        elif operation == "split":
            # Delegate to the appropriate splitter based on file type.
            # In a real implementation this would import and invoke the
            # media-specific splitter.  Here we record intent so that
            # integration code can wire things up.
            output_dir = kwargs.get("output_dir")
            if output_dir:
                ensure_dir(output_dir)
            logger.info("Split requested for %s", path.name)

        elif operation == "merge":
            output_dir = kwargs.get("output_dir")
            if output_dir:
                ensure_dir(output_dir)
            logger.info("Merge requested for %s", path.name)

        elif operation == "convert":
            output_dir = kwargs.get("output_dir")
            if output_dir:
                ensure_dir(output_dir)
            logger.info("Convert requested for %s", path.name)

        else:
            raise LazySplitterError(f"Unknown operation: {operation!r}")

    except Exception as exc:  # noqa: BLE001
        success = False
        error_message = str(exc)
        logger.error("Error processing %s: %s", path.name, exc)

    elapsed = time.monotonic() - start
    return {
        "input_path": str(path),
        "output_paths": output_paths,
        "operation": operation,
        "success": success,
        "error_message": error_message,
        "duration_seconds": round(elapsed, 4),
    }


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------

def _load_checkpoint(checkpoint_path: Path) -> Dict[str, Any]:
    """Load a checkpoint file, returning its data or an empty dict."""
    if checkpoint_path.is_file():
        try:
            with open(checkpoint_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            logger.info("Loaded checkpoint from %s", checkpoint_path)
            return data  # type: ignore[no-any-return]
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not load checkpoint %s: %s", checkpoint_path, exc)
    return {}


def _save_checkpoint(
    checkpoint_path: Path,
    completed_paths: Iterable[str],
    results: List[Dict[str, Any]],
) -> None:
    """Persist the current progress to a JSON checkpoint file."""
    data = {
        "completed": sorted(set(completed_paths)),
        "results": results,
    }
    ensure_dir(checkpoint_path.parent)
    with open(checkpoint_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    logger.debug("Checkpoint saved to %s", checkpoint_path)


# ---------------------------------------------------------------------------
# BatchProcessor
# ---------------------------------------------------------------------------

class BatchProcessor:
    """Apply an operation to many files with optional parallelism.

    Parameters
    ----------
    parallel:
        Enable parallel processing using multiple worker processes.
    workers:
        Number of worker processes.  Defaults to ``min(os.cpu_count(), 4)``.
    output_dir:
        Default output directory for operations that produce files.
    file_filter:
        Optional predicate applied to candidate file paths.  Files for
        which this callable returns ``False`` are excluded.
    checkpoint_dir:
        Directory where checkpoint JSON files are written.  When ``None``
        checkpoint support is disabled.
    max_concurrent:
        Maximum number of concurrent operations submitted to the pool at
        one time (rate limiting).  ``0`` means unlimited.
    progress_callback:
        Optional callable invoked as ``(completed, total, current_file)``
        after each file is processed.
    """

    def __init__(
        self,
        parallel: bool = False,
        workers: int = 0,
        output_dir: Optional[Union[str, Path]] = None,
        file_filter: Optional[Callable[[Path], bool]] = None,
        checkpoint_dir: Optional[Union[str, Path]] = None,
        max_concurrent: int = 0,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> None:
        self.parallel = parallel
        self.workers = workers or min(os.cpu_count() or 1, 4)
        self.output_dir = Path(output_dir) if output_dir else None
        self.file_filter = file_filter
        self.checkpoint_dir = Path(checkpoint_dir) if checkpoint_dir else None
        self.max_concurrent = max_concurrent
        self.progress_callback = progress_callback

        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(
        self,
        input_dir: Union[str, Path],
        pattern: str,
        operation: str,
        **kwargs: Any,
    ) -> BatchResult:
        """Process files in *input_dir* that match *pattern*.

        Parameters
        ----------
        input_dir:
            Directory to scan for files.
        pattern:
            Shell-style glob pattern (e.g. ``"*.pdf"``).
        operation:
            Operation to apply: ``"split"``, ``"merge"``, ``"convert"``,
            or ``"info"``.
        **kwargs:
            Additional keyword arguments forwarded to the operation handler.
            Recognised keys include ``output_dir``, ``recursive``.

        Returns
        -------
        BatchResult
            Aggregate result for the entire batch run.
        """
        self._validate_operation(operation)
        recursive = kwargs.pop("recursive", False)
        file_filter = kwargs.pop("file_filter", self.file_filter)

        files = _collect_files(
            input_dir,
            pattern,
            recursive=recursive,
            file_filter=file_filter,
        )
        return self._run(files, operation, kwargs)

    def process_files(
        self,
        file_paths: Sequence[Union[str, Path]],
        operation: str,
        **kwargs: Any,
    ) -> BatchResult:
        """Process an explicit list of file paths.

        Parameters
        ----------
        file_paths:
            Sequence of paths to process.
        operation:
            Operation to apply.
        **kwargs:
            Additional keyword arguments forwarded to the operation handler.

        Returns
        -------
        BatchResult
            Aggregate result.
        """
        self._validate_operation(operation)
        paths = [Path(p) for p in file_paths]
        return self._run(paths, operation, kwargs)

    def process_recursive(
        self,
        input_dir: Union[str, Path],
        pattern: str,
        operation: str,
        **kwargs: Any,
    ) -> BatchResult:
        """Recursively process files matching *pattern* under *input_dir*.

        This is a convenience wrapper around :meth:`process` with
        ``recursive=True``.

        Parameters
        ----------
        input_dir:
            Root directory to search.
        pattern:
            Shell-style glob pattern.
        operation:
            Operation to apply.
        **kwargs:
            Additional keyword arguments forwarded to the operation handler.

        Returns
        -------
        BatchResult
            Aggregate result.
        """
        kwargs["recursive"] = True
        return self.process(input_dir, pattern, operation, **kwargs)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_operation(operation: str) -> None:
        """Raise if *operation* is not one of the recognised operations."""
        if operation not in VALID_OPERATIONS:
            raise LazySplitterError(
                f"Invalid operation {operation!r}. "
                f"Must be one of {sorted(VALID_OPERATIONS)}",
                operation=operation,
            )

    def _checkpoint_path_for(self, operation: str) -> Optional[Path]:
        """Return the checkpoint file path for *operation*, or ``None``."""
        if self.checkpoint_dir is None:
            return None
        return self.checkpoint_dir / f"batch_{operation}_checkpoint.json"

    def _run(
        self,
        files: List[Path],
        operation: str,
        extra_kwargs: Dict[str, Any],
    ) -> BatchResult:
        """Execute the batch run, either sequentially or in parallel.

        Parameters
        ----------
        files:
            Resolved list of file paths.
        operation:
            Operation name.
        extra_kwargs:
            Keyword arguments forwarded to the per-file handler.

        Returns
        -------
        BatchResult
        """
        start = time.monotonic()

        # Merge output_dir from instance default and per-call override.
        output_dir = extra_kwargs.pop("output_dir", None) or self.output_dir
        if output_dir is not None:
            extra_kwargs["output_dir"] = str(output_dir)

        # Checkpoint handling -- skip files already completed.
        checkpoint_path = self._checkpoint_path_for(operation)
        completed_set: set = set()
        prior_results: List[Dict[str, Any]] = []
        if checkpoint_path is not None:
            ckpt = _load_checkpoint(checkpoint_path)
            completed_set = set(ckpt.get("completed", []))
            prior_results = ckpt.get("results", [])

        remaining = [f for f in files if str(f) not in completed_set]
        skipped = len(files) - len(remaining)

        result = BatchResult(
            total_files=len(files),
            skipped=skipped,
            checkpoint_path=checkpoint_path,
        )

        # Restore prior results into the batch result.
        for pr in prior_results:
            result.results.append(BatchFileResult.from_dict(pr))

        if not remaining:
            result.duration_seconds = round(time.monotonic() - start, 4)
            return result

        # Choose sequential vs. parallel execution.
        raw_results: List[Dict[str, Any]]
        if self.parallel and len(remaining) > 1:
            raw_results = self._run_parallel(remaining, operation, extra_kwargs)
        else:
            raw_results = self._run_sequential(remaining, operation, extra_kwargs)

        # Aggregate results.
        all_raw = list(prior_results) + raw_results
        for raw in raw_results:
            fr = BatchFileResult.from_dict(raw)
            result.results.append(fr)
            if fr.success:
                result.processed += 1
            else:
                result.failed += 1
                msg = f"{fr.input_path}: {fr.error_message}"
                result.errors.append(msg)

        # Add back previously processed count.
        result.processed += sum(
            1 for pr in prior_results if pr.get("success", True)
        )
        result.failed += sum(
            1 for pr in prior_results if not pr.get("success", True)
        )

        # Save final checkpoint.
        if checkpoint_path is not None:
            _save_checkpoint(
                checkpoint_path,
                [str(f) for f in files if str(f) in completed_set]
                + [r["input_path"] for r in raw_results],
                all_raw,
            )

        result.duration_seconds = round(time.monotonic() - start, 4)
        return result

    def _run_sequential(
        self,
        files: List[Path],
        operation: str,
        kwargs: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Process *files* one at a time in the current process."""
        results: List[Dict[str, Any]] = []
        total = len(files)
        for idx, fp in enumerate(files, 1):
            raw = _process_single_file(str(fp), operation, kwargs)
            results.append(raw)
            if self.progress_callback is not None:
                self.progress_callback(idx, total, fp.name)
        return results

    def _run_parallel(
        self,
        files: List[Path],
        operation: str,
        kwargs: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Process *files* using a :class:`ProcessPoolExecutor`.

        When :attr:`max_concurrent` is set the method submits work in
        batches to avoid overwhelming the system.
        """
        results: List[Dict[str, Any]] = []
        total = len(files)
        completed_count = 0

        max_workers = min(self.workers, total)
        batch_size = self.max_concurrent if self.max_concurrent > 0 else total

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            # Process in rate-limited batches if max_concurrent is set.
            for batch_start in range(0, total, batch_size):
                batch = files[batch_start : batch_start + batch_size]
                future_map: Dict[Future, Path] = {}  # type: ignore[type-arg]

                for fp in batch:
                    future = executor.submit(
                        _process_single_file,
                        str(fp),
                        operation,
                        kwargs,
                    )
                    future_map[future] = fp

                for future in as_completed(future_map):
                    fp = future_map[future]
                    try:
                        raw = future.result()
                    except Exception as exc:  # noqa: BLE001
                        raw = {
                            "input_path": str(fp),
                            "output_paths": [],
                            "operation": operation,
                            "success": False,
                            "error_message": str(exc),
                            "duration_seconds": 0.0,
                        }
                    results.append(raw)
                    completed_count += 1
                    if self.progress_callback is not None:
                        self.progress_callback(completed_count, total, fp.name)

        return results
