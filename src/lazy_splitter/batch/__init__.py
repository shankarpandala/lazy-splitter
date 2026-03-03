"""Batch processing, directory watching, and pipelines for lazy-splitter.

This sub-package provides three main entry points:

* :class:`BatchProcessor` -- apply an operation to many files at once,
  with optional parallelism, checkpointing, and progress tracking.
* :class:`DirectoryWatcher` -- monitor a directory for new or modified
  files and process them automatically.
* :class:`Pipeline` -- chain multiple operations into a multi-step
  workflow.

Data models consumed and produced by these classes live in
:mod:`lazy_splitter.batch.models`.
"""

from __future__ import annotations

from lazy_splitter.batch.models import (
    BatchFileResult,
    BatchResult,
    PipelineResult,
    WatchEvent,
)
from lazy_splitter.batch.pipeline import Pipeline, PipelineStep
from lazy_splitter.batch.processor import BatchProcessor
from lazy_splitter.batch.watcher import DirectoryWatcher

__all__ = [
    # Processor
    "BatchProcessor",
    # Watcher
    "DirectoryWatcher",
    # Pipeline
    "Pipeline",
    "PipelineStep",
    # Models
    "BatchFileResult",
    "BatchResult",
    "PipelineResult",
    "WatchEvent",
]
