"""Multi-step processing pipelines for lazy-splitter.

A :class:`Pipeline` chains several operations (detect, split, convert,
merge, or a custom callable) into a single executable workflow.  Pipelines
can be built programmatically or loaded from a TOML file / plain dict.

Error handling per step is configurable: the pipeline can *skip* the
failing file and continue, *abort* the entire run, or *retry* the step
a fixed number of times.
"""

from __future__ import annotations

import copy
import logging
import time
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Sequence,
    Union,
)

from lazy_splitter.core.exceptions import LazySplitterError
from lazy_splitter.core.utils import detect_file_type, ensure_dir

from lazy_splitter.batch.models import (
    BatchFileResult,
    BatchResult,
    PipelineResult,
)

logger = logging.getLogger(__name__)

# Recognised built-in step operation names.
BUILTIN_OPERATIONS = frozenset({"detect", "split", "convert", "merge"})

# Error-handling strategies.
ON_ERROR_SKIP = "skip"
ON_ERROR_ABORT = "abort"
ON_ERROR_RETRY = "retry"
VALID_ERROR_STRATEGIES = frozenset({ON_ERROR_SKIP, ON_ERROR_ABORT, ON_ERROR_RETRY})


# ---------------------------------------------------------------------------
# PipelineStep
# ---------------------------------------------------------------------------

class PipelineStep:
    """A single step within a :class:`Pipeline`.

    Parameters
    ----------
    operation:
        Name of a built-in operation (``"detect"``, ``"split"``,
        ``"convert"``, ``"merge"``) **or** ``"custom"`` when a callable
        is provided.
    kwargs:
        Keyword arguments forwarded to the operation handler.
    on_error:
        Error-handling strategy: ``"skip"`` (default), ``"abort"``, or
        ``"retry"``.
    max_retries:
        Number of retries when *on_error* is ``"retry"``.
    custom_fn:
        A callable with signature ``(file_path: Path, **kwargs) -> List[Path]``
        used when *operation* is ``"custom"``.
    """

    def __init__(
        self,
        operation: str,
        kwargs: Optional[Dict[str, Any]] = None,
        on_error: str = ON_ERROR_SKIP,
        max_retries: int = 1,
        custom_fn: Optional[Callable[..., List[Path]]] = None,
    ) -> None:
        if operation not in BUILTIN_OPERATIONS and operation != "custom":
            raise LazySplitterError(
                f"Unknown pipeline operation {operation!r}. "
                f"Must be one of {sorted(BUILTIN_OPERATIONS)} or 'custom'.",
                operation=operation,
            )
        if on_error not in VALID_ERROR_STRATEGIES:
            raise LazySplitterError(
                f"Unknown error strategy {on_error!r}. "
                f"Must be one of {sorted(VALID_ERROR_STRATEGIES)}.",
                on_error=on_error,
            )
        if operation == "custom" and custom_fn is None:
            raise LazySplitterError(
                "A 'custom' step requires a custom_fn callable."
            )

        self.operation = operation
        self.kwargs: Dict[str, Any] = dict(kwargs or {})
        self.on_error = on_error
        self.max_retries = max(max_retries, 1)
        self.custom_fn = custom_fn

    def __repr__(self) -> str:
        return (
            f"PipelineStep(operation={self.operation!r}, "
            f"on_error={self.on_error!r})"
        )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class Pipeline:
    """Define and execute a multi-step file-processing pipeline.

    Parameters
    ----------
    steps:
        Optional initial sequence of :class:`PipelineStep` objects.  More
        steps can be appended later via :meth:`add_step`.

    Example
    -------
    >>> pipe = Pipeline()
    >>> pipe.add_step("detect")
    >>> pipe.add_step("split", output_dir="/tmp/out")
    >>> pipe.add_step("convert", target_format="epub")
    >>> result = pipe.execute([Path("book.pdf")])
    """

    def __init__(
        self,
        steps: Optional[Sequence[PipelineStep]] = None,
    ) -> None:
        self._steps: List[PipelineStep] = list(steps) if steps else []

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    def add_step(
        self,
        operation: str,
        on_error: str = ON_ERROR_SKIP,
        max_retries: int = 1,
        custom_fn: Optional[Callable[..., List[Path]]] = None,
        **kwargs: Any,
    ) -> "Pipeline":
        """Append a new step to the pipeline.

        Parameters
        ----------
        operation:
            Built-in operation name or ``"custom"``.
        on_error:
            Error-handling strategy.
        max_retries:
            Retries for the ``"retry"`` strategy.
        custom_fn:
            Callable for ``"custom"`` steps.
        **kwargs:
            Arguments forwarded to the operation handler.

        Returns
        -------
        Pipeline
            ``self``, for fluent chaining.
        """
        step = PipelineStep(
            operation=operation,
            kwargs=kwargs,
            on_error=on_error,
            max_retries=max_retries,
            custom_fn=custom_fn,
        )
        self._steps.append(step)
        return self

    @property
    def steps(self) -> List[PipelineStep]:
        """The ordered list of steps in this pipeline."""
        return list(self._steps)

    @property
    def step_count(self) -> int:
        """Number of steps currently in the pipeline."""
        return len(self._steps)

    # ------------------------------------------------------------------
    # Factory: from dict / TOML
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> "Pipeline":
        """Build a pipeline from a plain dictionary.

        The dictionary should have a ``"steps"`` key containing a list of
        step definitions.  Each step definition is a dict with at least an
        ``"operation"`` key and optional ``"on_error"``, ``"max_retries"``,
        and arbitrary keyword arguments.

        Parameters
        ----------
        config:
            Pipeline definition dictionary.

        Returns
        -------
        Pipeline
            The constructed pipeline.

        Example
        -------
        >>> cfg = {
        ...     "steps": [
        ...         {"operation": "detect"},
        ...         {"operation": "split", "output_dir": "/tmp/out"},
        ...     ]
        ... }
        >>> pipe = Pipeline.from_dict(cfg)
        """
        steps_data = config.get("steps", [])
        if not isinstance(steps_data, list):
            raise LazySplitterError(
                "Pipeline config 'steps' must be a list",
                config=config,
            )

        pipeline = cls()
        for step_def in steps_data:
            if not isinstance(step_def, dict):
                raise LazySplitterError(
                    f"Each pipeline step must be a dict, got {type(step_def).__name__}",
                )
            step_def = dict(step_def)  # shallow copy
            operation = step_def.pop("operation", None)
            if operation is None:
                raise LazySplitterError(
                    "Pipeline step missing required 'operation' key",
                )
            on_error = step_def.pop("on_error", ON_ERROR_SKIP)
            max_retries = step_def.pop("max_retries", 1)
            pipeline.add_step(
                operation=operation,
                on_error=on_error,
                max_retries=max_retries,
                **step_def,
            )
        return pipeline

    @classmethod
    def from_toml(cls, toml_path: Union[str, Path]) -> "Pipeline":
        """Build a pipeline from a TOML configuration file.

        The TOML file must contain a ``[pipeline]`` table with a
        ``steps`` array of tables.

        Parameters
        ----------
        toml_path:
            Path to the TOML file.

        Returns
        -------
        Pipeline
            The constructed pipeline.
        """
        path = Path(toml_path)
        if not path.is_file():
            raise LazySplitterError(
                f"TOML config file not found: {path}",
                path=str(path),
            )

        # Python 3.11+ has tomllib; earlier versions need tomli.
        try:
            import tomllib  # type: ignore[import-not-found]
        except ModuleNotFoundError:
            try:
                import tomli as tomllib  # type: ignore[no-redef]
            except ModuleNotFoundError:
                raise LazySplitterError(
                    "Reading TOML files requires Python 3.11+ or the "
                    "'tomli' package.  Install it with: pip install tomli"
                )

        with open(path, "rb") as fh:
            data = tomllib.load(fh)

        pipeline_cfg = data.get("pipeline", data)
        return cls.from_dict(pipeline_cfg)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(
        self,
        input_paths: Sequence[Union[str, Path]],
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> PipelineResult:
        """Execute the pipeline on the given input files.

        Each step receives the output paths of the previous step as its
        input, forming a chain.  The very first step receives
        *input_paths*.

        Parameters
        ----------
        input_paths:
            Initial files to feed into the first step.
        progress_callback:
            Optional callable invoked as
            ``(step_index, total_steps, operation_name)`` before each step.

        Returns
        -------
        PipelineResult
            Aggregate result describing every step's outcome.
        """
        if not self._steps:
            raise LazySplitterError("Pipeline has no steps to execute")

        result = PipelineResult(
            total_steps=len(self._steps),
        )

        # The "current files" flowing through the pipeline.
        current_paths: List[Path] = [Path(p) for p in input_paths]

        for step_idx, step in enumerate(self._steps):
            if progress_callback is not None:
                progress_callback(step_idx, len(self._steps), step.operation)

            logger.info(
                "Pipeline step %d/%d: %s (%d files)",
                step_idx + 1,
                len(self._steps),
                step.operation,
                len(current_paths),
            )

            step_result, next_paths = self._execute_step(
                step, current_paths, step_idx
            )
            result.results_per_step[step_idx] = step_result

            if step_result.failed > 0 and step.on_error == ON_ERROR_ABORT:
                logger.error(
                    "Aborting pipeline at step %d due to errors", step_idx + 1
                )
                result.success = False
                return result

            result.steps_completed += 1
            current_paths = next_paths

        result.success = all(
            sr.failed == 0 for sr in result.results_per_step.values()
        )
        return result

    # ------------------------------------------------------------------
    # Internal: per-step execution
    # ------------------------------------------------------------------

    def _execute_step(
        self,
        step: PipelineStep,
        paths: List[Path],
        step_index: int,
    ) -> tuple:
        """Run a single pipeline step over *paths*.

        Returns
        -------
        tuple of (BatchResult, list of Path)
            The batch result and the list of output paths to pass to the
            next step.
        """
        start = time.monotonic()
        batch = BatchResult(total_files=len(paths))
        next_paths: List[Path] = []

        for fp in paths:
            file_result = self._process_file_with_retry(step, fp)
            batch.results.append(file_result)

            if file_result.success:
                batch.processed += 1
                if file_result.output_paths:
                    next_paths.extend(file_result.output_paths)
                else:
                    # If the step didn't produce new files (e.g. "detect"),
                    # pass the input through.
                    next_paths.append(fp)
            else:
                batch.failed += 1
                msg = f"{file_result.input_path}: {file_result.error_message}"
                batch.errors.append(msg)

                if step.on_error == ON_ERROR_SKIP:
                    # Still pass the original file forward so subsequent
                    # steps can try.
                    next_paths.append(fp)
                elif step.on_error == ON_ERROR_ABORT:
                    break

        batch.duration_seconds = round(time.monotonic() - start, 4)
        return batch, next_paths

    def _process_file_with_retry(
        self,
        step: PipelineStep,
        file_path: Path,
    ) -> BatchFileResult:
        """Attempt to process *file_path* with up to *step.max_retries* tries."""
        last_error: Optional[str] = None
        attempts = step.max_retries if step.on_error == ON_ERROR_RETRY else 1

        for attempt in range(1, attempts + 1):
            result = self._run_operation(step, file_path)
            if result.success:
                return result
            last_error = result.error_message
            if attempt < attempts:
                logger.warning(
                    "Retry %d/%d for %s (step=%s): %s",
                    attempt,
                    attempts,
                    file_path.name,
                    step.operation,
                    last_error,
                )

        # All attempts exhausted.
        return BatchFileResult(
            input_path=file_path,
            operation=step.operation,
            success=False,
            error_message=last_error,
        )

    @staticmethod
    def _run_operation(
        step: PipelineStep,
        file_path: Path,
    ) -> BatchFileResult:
        """Execute the operation defined by *step* on *file_path*.

        For built-in operations this method performs lightweight handling;
        real processing is expected to be wired up by the integrating
        application.  For ``"custom"`` steps the user-supplied callable is
        invoked directly.
        """
        start = time.monotonic()
        output_paths: List[Path] = []
        error_message: Optional[str] = None
        success = True

        try:
            if step.operation == "custom" and step.custom_fn is not None:
                result_paths = step.custom_fn(file_path, **step.kwargs)
                output_paths = [Path(p) for p in (result_paths or [])]

            elif step.operation == "detect":
                # Detection does not produce new files; it annotates.
                _file_type = detect_file_type(file_path)
                logger.debug("Detected type for %s: %s", file_path.name, _file_type)

            elif step.operation == "split":
                output_dir = step.kwargs.get("output_dir")
                if output_dir:
                    ensure_dir(output_dir)
                logger.debug("Split requested for %s", file_path.name)

            elif step.operation == "convert":
                output_dir = step.kwargs.get("output_dir")
                if output_dir:
                    ensure_dir(output_dir)
                logger.debug("Convert requested for %s", file_path.name)

            elif step.operation == "merge":
                output_dir = step.kwargs.get("output_dir")
                if output_dir:
                    ensure_dir(output_dir)
                logger.debug("Merge requested for %s", file_path.name)

        except Exception as exc:  # noqa: BLE001
            success = False
            error_message = str(exc)
            logger.error(
                "Step %s failed for %s: %s",
                step.operation,
                file_path.name,
                exc,
            )

        elapsed = round(time.monotonic() - start, 4)
        return BatchFileResult(
            input_path=file_path,
            output_paths=output_paths,
            operation=step.operation,
            success=success,
            error_message=error_message,
            duration_seconds=elapsed,
        )
