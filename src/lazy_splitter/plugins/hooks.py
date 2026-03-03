"""Event hook system for pre/post processing callbacks.

The :class:`HookManager` allows plugins and user code to register callbacks
for lifecycle events (e.g. ``pre_split``, ``post_detect``) without modifying
the core splitting pipeline.  Both synchronous and asynchronous callbacks
are supported.

Supported events:
    ``pre_detect``   -- fired before chapter detection starts.
    ``post_detect``  -- fired after detection completes.
    ``pre_split``    -- fired before a split operation.
    ``post_split``   -- fired after a split operation.
    ``pre_merge``    -- fired before a merge operation.
    ``post_merge``   -- fired after a merge operation.
    ``on_error``     -- fired when a recoverable error occurs.

Usage::

    from lazy_splitter.plugins.hooks import HookManager

    hooks = HookManager()

    def my_callback(**kwargs):
        print("Split starting!", kwargs)

    hooks.register_hook("pre_split", my_callback)
    hooks.emit("pre_split", file_path="/tmp/doc.pdf", chapters=5)

A module-level singleton is available via :func:`get_hook_manager`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supported events
# ---------------------------------------------------------------------------

#: Canonical list of hook event names recognised by the system.
HOOK_EVENTS: List[str] = [
    "pre_detect",
    "post_detect",
    "pre_split",
    "post_split",
    "pre_merge",
    "post_merge",
    "pre_convert",
    "post_convert",
    "on_error",
    "on_progress",
]


# ---------------------------------------------------------------------------
# HookManager
# ---------------------------------------------------------------------------

class HookManager:
    """Manages event hooks for the splitting pipeline.

    Hooks are callbacks invoked before and after key operations, enabling
    plugins and user code to customise behaviour without touching core logic.
    Each callback receives keyword arguments specific to the event being
    emitted.
    """

    def __init__(self) -> None:
        self._hooks: Dict[str, List[Callable[..., Any]]] = {
            event: [] for event in HOOK_EVENTS
        }

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_hook(self, event: str, callback: Callable[..., Any]) -> None:
        """Register a callback for *event*.

        Parameters:
            event: Event name (e.g. ``"pre_split"``, ``"post_detect"``).
            callback: Callable that accepts ``**kwargs``.  Both sync and
                async callables are accepted.

        Raises:
            ValueError: If *event* is not a recognised event name.
        """
        if event not in self._hooks:
            raise ValueError(
                f"Unknown hook event: {event!r}. "
                f"Supported events: {', '.join(HOOK_EVENTS)}"
            )
        self._hooks[event].append(callback)
        logger.debug("Registered hook for event %r: %s", event, callback)

    # Keep the short alias used by the existing codebase.
    register = register_hook

    def unregister(self, event: str, callback: Callable[..., Any]) -> None:
        """Remove a previously registered hook callback.

        If the callback is not registered for *event* the call is a no-op.

        Parameters:
            event: Event name.
            callback: The callback to remove.
        """
        if event in self._hooks:
            try:
                self._hooks[event].remove(callback)
                logger.debug("Unregistered hook for event %r: %s", event, callback)
            except ValueError:
                pass

    # ------------------------------------------------------------------
    # Emission
    # ------------------------------------------------------------------

    def emit(self, event: str, **kwargs: Any) -> List[Any]:
        """Fire an event, invoking all registered hooks in order.

        Both synchronous and asynchronous callbacks are supported:

        * **Sync** callbacks are called directly.
        * **Async** callbacks are awaited in a running event loop, or
          executed via :func:`asyncio.get_event_loop().run_until_complete`
          when no loop is active.

        Errors raised by individual hooks are logged and swallowed (except
        for ``on_error`` hooks, where exceptions propagate immediately) so
        that a misbehaving hook does not break the main pipeline.

        Parameters:
            event: Event name.
            **kwargs: Data to pass to each callback.

        Returns:
            List of return values from each callback (in registration
            order).  For async callbacks that were scheduled as tasks, the
            :class:`asyncio.Future` is included in the list.
        """
        if event not in self._hooks:
            return []

        results: List[Any] = []
        for callback in self._hooks[event]:
            try:
                result = callback(**kwargs)
                # Handle async callbacks transparently.
                if asyncio.iscoroutine(result):
                    try:
                        loop = asyncio.get_running_loop()
                        # Running inside an async context -- schedule.
                        future = asyncio.ensure_future(result)
                        results.append(future)
                    except RuntimeError:
                        # No running loop -- create one and block.
                        loop = asyncio.new_event_loop()
                        try:
                            result = loop.run_until_complete(result)
                        finally:
                            loop.close()
                        results.append(result)
                else:
                    results.append(result)
            except Exception as exc:
                logger.error(
                    "Hook %s for event %r raised an error: %s",
                    callback,
                    event,
                    exc,
                    exc_info=True,
                )
                # ``on_error`` hooks must not silently swallow exceptions.
                if event == "on_error":
                    raise

        return results

    # ------------------------------------------------------------------
    # Introspection / cleanup
    # ------------------------------------------------------------------

    def clear(self, event: Optional[str] = None) -> None:
        """Remove all hooks, or all hooks for a specific event.

        Parameters:
            event: If given, clear only hooks for this event.  If ``None``,
                clear hooks for **all** events.
        """
        if event is not None:
            if event in self._hooks:
                self._hooks[event].clear()
        else:
            for hooks_list in self._hooks.values():
                hooks_list.clear()

    def get_hooks(self, event: str) -> List[Callable[..., Any]]:
        """Return a copy of the hooks registered for *event*.

        Parameters:
            event: Event name.

        Returns:
            List of registered callbacks (empty if *event* is unknown or
            has no hooks).
        """
        return list(self._hooks.get(event, []))

    @property
    def registered_events(self) -> List[str]:
        """Return event names that have at least one hook registered.

        Returns:
            Sorted list of event name strings.
        """
        return sorted(event for event, hooks in self._hooks.items() if hooks)


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_global_hooks: Optional[HookManager] = None


def get_hook_manager() -> HookManager:
    """Return the global :class:`HookManager` singleton.

    The instance is created on first call and reused thereafter.

    Returns:
        The shared :class:`HookManager` instance.
    """
    global _global_hooks
    if _global_hooks is None:
        _global_hooks = HookManager()
    return _global_hooks
