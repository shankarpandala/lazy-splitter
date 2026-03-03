"""Batch-specific data models for the lazy-splitter batch module.

These dataclasses represent the results and events produced by batch
processing, pipeline execution, and directory watching.  They are
intentionally kept lightweight and serialisable so that they can be
written to checkpoint files or transmitted over IPC boundaries.
"""

from __future__ import annotations

import dataclasses
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclasses.dataclass
class BatchFileResult:
    """The outcome of a single file operation within a batch run.

    Attributes
    ----------
    input_path:
        Path to the source file that was processed.
    output_paths:
        Paths to all files produced by the operation.
    operation:
        Name of the operation that was applied (e.g. ``"split"``).
    success:
        ``True`` if the operation completed without error.
    error_message:
        Human-readable error description, or ``None`` on success.
    duration_seconds:
        Wall-clock time in seconds consumed by this single file.
    """

    input_path: Path
    output_paths: List[Path] = dataclasses.field(default_factory=list)
    operation: str = ""
    success: bool = True
    error_message: Optional[str] = None
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a JSON-safe dictionary."""
        return {
            "input_path": str(self.input_path),
            "output_paths": [str(p) for p in self.output_paths],
            "operation": self.operation,
            "success": self.success,
            "error_message": self.error_message,
            "duration_seconds": self.duration_seconds,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BatchFileResult":
        """Reconstruct from a dictionary (e.g. loaded from a checkpoint)."""
        return cls(
            input_path=Path(data["input_path"]),
            output_paths=[Path(p) for p in data.get("output_paths", [])],
            operation=data.get("operation", ""),
            success=data.get("success", True),
            error_message=data.get("error_message"),
            duration_seconds=data.get("duration_seconds", 0.0),
        )


@dataclasses.dataclass
class BatchResult:
    """Aggregate result for an entire batch run.

    Attributes
    ----------
    total_files:
        Total number of files that were considered.
    processed:
        Number of files that were successfully processed.
    failed:
        Number of files that failed during processing.
    skipped:
        Number of files skipped (e.g. already in checkpoint).
    errors:
        List of ``(path, error_message)`` pairs for failed files.
    results:
        Per-file result objects.
    duration_seconds:
        Wall-clock time in seconds for the entire batch run.
    checkpoint_path:
        Path to the checkpoint JSON file, or ``None`` if checkpointing
        was not enabled.
    """

    total_files: int = 0
    processed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: List[str] = dataclasses.field(default_factory=list)
    results: List[BatchFileResult] = dataclasses.field(default_factory=list)
    duration_seconds: float = 0.0
    checkpoint_path: Optional[Path] = None

    @property
    def success_rate(self) -> float:
        """Return the fraction of files that succeeded (0.0 -- 1.0)."""
        if self.total_files == 0:
            return 0.0
        return self.processed / self.total_files

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a JSON-safe dictionary."""
        return {
            "total_files": self.total_files,
            "processed": self.processed,
            "failed": self.failed,
            "skipped": self.skipped,
            "errors": self.errors,
            "results": [r.to_dict() for r in self.results],
            "duration_seconds": self.duration_seconds,
            "checkpoint_path": str(self.checkpoint_path)
            if self.checkpoint_path
            else None,
        }


@dataclasses.dataclass
class PipelineResult:
    """Aggregate result of a multi-step pipeline execution.

    Attributes
    ----------
    steps_completed:
        Number of pipeline steps that finished successfully.
    total_steps:
        Total number of steps defined in the pipeline.
    results_per_step:
        Mapping from step index to its :class:`BatchResult`.
    success:
        ``True`` when every step completed without a fatal error.
    """

    steps_completed: int = 0
    total_steps: int = 0
    results_per_step: Dict[int, BatchResult] = dataclasses.field(
        default_factory=dict,
    )
    success: bool = True


@dataclasses.dataclass
class WatchEvent:
    """A single filesystem event captured by the directory watcher.

    Attributes
    ----------
    event_type:
        One of ``"created"``, ``"modified"``, ``"moved"``.
    file_path:
        Path to the affected file.
    timestamp:
        When the event was observed.
    processed:
        ``True`` once the event has been handled by the watcher callback.
    """

    event_type: str
    file_path: Path
    timestamp: datetime.datetime = dataclasses.field(
        default_factory=datetime.datetime.utcnow,
    )
    processed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a JSON-safe dictionary."""
        return {
            "event_type": self.event_type,
            "file_path": str(self.file_path),
            "timestamp": self.timestamp.isoformat(),
            "processed": self.processed,
        }
