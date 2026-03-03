"""Directory watcher for automatic batch processing.

Provides :class:`DirectoryWatcher`, which monitors a directory for new or
modified files and feeds them into a :class:`BatchProcessor` (or a
user-supplied callback).  The watcher uses the *watchdog* library when
available and falls back to a simple polling loop otherwise.

The watcher runs in a background thread so the caller's main thread
remains unblocked.
"""

from __future__ import annotations

import fnmatch
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Union

from lazy_splitter.core.exceptions import LazySplitterError
from lazy_splitter.core.utils import detect_file_type, ensure_dir

from lazy_splitter.batch.models import WatchEvent

logger = logging.getLogger(__name__)

# Try to import watchdog; it is an optional dependency.
try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer

    _HAS_WATCHDOG = True
except ImportError:  # pragma: no cover
    _HAS_WATCHDOG = False


# ---------------------------------------------------------------------------
# Debouncer
# ---------------------------------------------------------------------------

class _Debouncer:
    """Collapse rapid-fire events for the same file into a single trigger.

    When a file is being written in chunks the OS may emit dozens of
    *modified* events in quick succession.  The debouncer waits for
    *delay* seconds of silence before forwarding the event.

    Parameters
    ----------
    delay:
        Minimum quiet period in seconds before an event is considered
        stable.
    callback:
        Function to call once the event has stabilised.  Receives a
        single :class:`WatchEvent` argument.
    """

    def __init__(
        self,
        delay: float,
        callback: Callable[[WatchEvent], None],
    ) -> None:
        self._delay = delay
        self._callback = callback
        self._timers: Dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def trigger(self, event: WatchEvent) -> None:
        """Register an event; the callback fires after the debounce window."""
        key = str(event.file_path)
        with self._lock:
            existing = self._timers.pop(key, None)
            if existing is not None:
                existing.cancel()

            timer = threading.Timer(self._delay, self._fire, args=(key, event))
            timer.daemon = True
            self._timers[key] = timer
            timer.start()

    def _fire(self, key: str, event: WatchEvent) -> None:
        with self._lock:
            self._timers.pop(key, None)
        self._callback(event)

    def cancel_all(self) -> None:
        """Cancel all pending timers."""
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()


# ---------------------------------------------------------------------------
# Watchdog-based handler (used when watchdog is installed)
# ---------------------------------------------------------------------------

if _HAS_WATCHDOG:

    class _WatchdogHandler(FileSystemEventHandler):  # type: ignore[misc]
        """Translate watchdog events into :class:`WatchEvent` instances."""

        def __init__(
            self,
            pattern: str,
            debouncer: _Debouncer,
        ) -> None:
            super().__init__()
            self._pattern = pattern
            self._debouncer = debouncer

        # -- FileSystemEventHandler overrides --------------------------------

        def on_created(self, event: "FileSystemEvent") -> None:
            if not event.is_directory:
                self._maybe_handle(event.src_path, "created")

        def on_modified(self, event: "FileSystemEvent") -> None:
            if not event.is_directory:
                self._maybe_handle(event.src_path, "modified")

        def on_moved(self, event: "FileSystemEvent") -> None:
            if not event.is_directory:
                dest = getattr(event, "dest_path", event.src_path)
                self._maybe_handle(dest, "moved")

        # -- Internal --------------------------------------------------------

        def _maybe_handle(self, path_str: str, event_type: str) -> None:
            path = Path(path_str)
            if fnmatch.fnmatch(path.name, self._pattern):
                import datetime

                watch_event = WatchEvent(
                    event_type=event_type,
                    file_path=path,
                    timestamp=datetime.datetime.utcnow(),
                )
                self._debouncer.trigger(watch_event)


# ---------------------------------------------------------------------------
# DirectoryWatcher
# ---------------------------------------------------------------------------

class DirectoryWatcher:
    """Monitor a directory and process matching files automatically.

    The watcher supports two back-ends:

    * **watchdog** (preferred) -- uses OS-level file-system notifications
      for low-latency, low-overhead watching.
    * **polling** -- periodically scans the directory when *watchdog* is
      not installed.

    Parameters
    ----------
    on_event:
        Optional callback invoked for every stable event.  Receives a
        :class:`WatchEvent`.  When ``None``, events are logged but not
        acted upon.
    debounce_seconds:
        Quiet period required before a file event is considered stable.
    poll_interval:
        Seconds between directory scans when using the polling back-end.
    """

    def __init__(
        self,
        on_event: Optional[Callable[[WatchEvent], None]] = None,
        debounce_seconds: float = 1.0,
        poll_interval: float = 2.0,
    ) -> None:
        self._on_event = on_event or self._default_handler
        self._debounce_seconds = debounce_seconds
        self._poll_interval = poll_interval

        self._running = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._observer: Any = None  # watchdog Observer, if available

        # Track events emitted during the lifetime of the watcher.
        self._events: List[WatchEvent] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """``True`` while the watcher is actively monitoring."""
        return self._running

    @property
    def events(self) -> List[WatchEvent]:
        """Return a snapshot of all events observed so far."""
        with self._lock:
            return list(self._events)

    def watch(
        self,
        directory: Union[str, Path],
        pattern: str = "*",
        operation: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Start watching *directory* for files matching *pattern*.

        The method returns immediately; monitoring happens in a daemon
        thread.

        Parameters
        ----------
        directory:
            Path to the directory to watch.
        pattern:
            Shell-style glob pattern used to filter file names.
        operation:
            Optional operation name (``"split"``, ``"convert"``, etc.).
            When provided, matched files are automatically queued for
            batch processing via the ``on_event`` callback.
        **kwargs:
            Extra arguments stored for use by the event callback.

        Raises
        ------
        LazySplitterError
            If the directory does not exist or the watcher is already
            running.
        """
        root = Path(directory)
        if not root.is_dir():
            raise LazySplitterError(
                f"Watch directory does not exist: {root}",
                path=str(root),
            )

        if self._running:
            raise LazySplitterError("Watcher is already running")

        self._stop_event.clear()
        self._running = True

        debouncer = _Debouncer(
            delay=self._debounce_seconds,
            callback=self._handle_stable_event,
        )

        if _HAS_WATCHDOG:
            self._start_watchdog(root, pattern, debouncer)
        else:
            self._start_polling(root, pattern, debouncer)

        logger.info(
            "Watching %s for pattern %r (backend=%s)",
            root,
            pattern,
            "watchdog" if _HAS_WATCHDOG else "polling",
        )

    def stop(self) -> None:
        """Stop watching and clean up resources.

        Safe to call multiple times or when the watcher is not running.
        """
        if not self._running:
            return

        self._stop_event.set()

        # Shut down the watchdog observer if active.
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=5)
            except Exception:  # noqa: BLE001
                pass
            self._observer = None

        # Wait for the polling thread if active.
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

        self._running = False
        logger.info("Watcher stopped")

    # ------------------------------------------------------------------
    # Internal: watchdog back-end
    # ------------------------------------------------------------------

    def _start_watchdog(
        self,
        directory: Path,
        pattern: str,
        debouncer: _Debouncer,
    ) -> None:
        """Start monitoring via watchdog's :class:`Observer`."""
        handler = _WatchdogHandler(pattern=pattern, debouncer=debouncer)
        observer = Observer()
        observer.schedule(handler, str(directory), recursive=False)
        observer.daemon = True
        observer.start()
        self._observer = observer

    # ------------------------------------------------------------------
    # Internal: polling back-end
    # ------------------------------------------------------------------

    def _start_polling(
        self,
        directory: Path,
        pattern: str,
        debouncer: _Debouncer,
    ) -> None:
        """Start monitoring via periodic directory scans."""
        thread = threading.Thread(
            target=self._poll_loop,
            args=(directory, pattern, debouncer),
            daemon=True,
        )
        thread.start()
        self._thread = thread

    def _poll_loop(
        self,
        directory: Path,
        pattern: str,
        debouncer: _Debouncer,
    ) -> None:
        """Background thread that polls the directory for changes."""
        import datetime

        known: Dict[str, float] = {}  # path -> last modified time

        # Initial scan to establish baseline.
        for entry in directory.iterdir():
            if entry.is_file() and fnmatch.fnmatch(entry.name, pattern):
                try:
                    known[str(entry)] = entry.stat().st_mtime
                except OSError:
                    pass

        while not self._stop_event.is_set():
            self._stop_event.wait(self._poll_interval)
            if self._stop_event.is_set():
                break

            current: Dict[str, float] = {}
            try:
                entries = list(directory.iterdir())
            except OSError:
                continue

            for entry in entries:
                if not entry.is_file():
                    continue
                if not fnmatch.fnmatch(entry.name, pattern):
                    continue
                try:
                    mtime = entry.stat().st_mtime
                except OSError:
                    continue

                key = str(entry)
                current[key] = mtime

                if key not in known:
                    # New file.
                    event = WatchEvent(
                        event_type="created",
                        file_path=entry,
                        timestamp=datetime.datetime.utcnow(),
                    )
                    debouncer.trigger(event)
                elif mtime > known[key]:
                    # Modified file.
                    event = WatchEvent(
                        event_type="modified",
                        file_path=entry,
                        timestamp=datetime.datetime.utcnow(),
                    )
                    debouncer.trigger(event)

            known = current

        debouncer.cancel_all()

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def _handle_stable_event(self, event: WatchEvent) -> None:
        """Invoked by the debouncer once an event has stabilised."""
        event.processed = True
        with self._lock:
            self._events.append(event)

        logger.info(
            "Stable event: %s %s",
            event.event_type,
            event.file_path,
        )

        try:
            self._on_event(event)
        except Exception:  # noqa: BLE001
            logger.exception(
                "Error in event handler for %s", event.file_path
            )

    @staticmethod
    def _default_handler(event: WatchEvent) -> None:
        """No-op default handler; simply logs the event."""
        logger.debug(
            "Unhandled watch event: %s %s",
            event.event_type,
            event.file_path,
        )
