"""Plugin base classes and registration decorators for lazy-splitter.

Provides abstract base classes for the four plugin categories --
:class:`StrategyPlugin`, :class:`FileTypePlugin`, :class:`OutputPlugin`,
and :class:`HookPlugin` -- as well as convenience decorators
(:func:`register_strategy`, :func:`register_file_handler`) that allow
classes to be registered simply by decorating them.

Example -- registering a custom detection strategy via decorator::

    from lazy_splitter.plugins.base import register_strategy

    @register_strategy("my_strategy")
    class MyDetector:
        def detect(self, input_path, **kwargs):
            ...

Example -- creating a full strategy plugin::

    from lazy_splitter.plugins.base import StrategyPlugin

    class MyPlugin(StrategyPlugin):
        @property
        def name(self) -> str:
            return "my-plugin"

        @property
        def version(self) -> str:
            return "1.0.0"

        def detect(self, input_path, **kwargs):
            ...
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type

from lazy_splitter.core.exceptions import PluginError

# ---------------------------------------------------------------------------
# Global registries populated by the decorators
# ---------------------------------------------------------------------------

_STRATEGY_REGISTRY: Dict[str, Type[Any]] = {}
"""Mapping of strategy name to detector class, populated by
:func:`register_strategy`."""

_FILE_HANDLER_REGISTRY: Dict[str, Type[Any]] = {}
"""Mapping of file extension to handler class, populated by
:func:`register_file_handler`."""


# ---------------------------------------------------------------------------
# Abstract base classes
# ---------------------------------------------------------------------------

class Plugin(ABC):
    """Abstract base class for all lazy-splitter plugins.

    Every plugin **must** provide a :attr:`name` and :attr:`version`.  An
    optional :attr:`description` can supply extra detail shown in listings.

    Lifecycle:
        1. The :class:`~lazy_splitter.plugins.manager.PluginManager`
           instantiates the class.
        2. :meth:`activate` is called once the instance is ready.
        3. :meth:`deactivate` is called when the plugin is unloaded.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique, human-readable plugin name."""
        ...  # pragma: no cover

    @property
    @abstractmethod
    def version(self) -> str:
        """Semantic version string (e.g. ``"1.2.3"``)."""
        ...  # pragma: no cover

    @property
    def description(self) -> str:
        """Optional one-line description of the plugin.

        Returns:
            A human-readable description, or ``""`` by default.
        """
        return ""

    def activate(self) -> None:
        """Called when the plugin is loaded and activated.

        Override this to perform one-time setup such as registering hooks
        or validating runtime dependencies.
        """

    def deactivate(self) -> None:
        """Called when the plugin is being unloaded.

        Override this to release resources or de-register hooks.
        """


class StrategyPlugin(Plugin):
    """Plugin that provides a custom chapter / segment detection strategy.

    Subclasses must implement :meth:`detect`, which receives a file path
    and returns a :class:`~lazy_splitter.core.models.DetectionResult` (or
    compatible object).

    The strategy is automatically registered under :attr:`strategy_name`
    when the plugin is loaded by the
    :class:`~lazy_splitter.plugins.manager.PluginManager`.
    """

    @abstractmethod
    def detect(self, input_path: Path, **kwargs: Any) -> Any:
        """Run detection using this strategy.

        Parameters:
            input_path: Path to the file to analyse.
            **kwargs: Strategy-specific options (sensitivity, language, etc.).

        Returns:
            A :class:`~lazy_splitter.core.models.DetectionResult` or
            compatible object describing the detected chapters / segments.
        """
        ...  # pragma: no cover

    @property
    def strategy_name(self) -> str:
        """Name under which this strategy is registered.

        Defaults to :attr:`name`; override if the registration name should
        differ from the human-readable plugin name.

        Returns:
            Strategy identifier string.
        """
        return self.name


class FileTypePlugin(Plugin):
    """Plugin that adds support for a new file type.

    Subclasses must expose :attr:`supported_extensions` and implement both
    :meth:`detect` (to find chapters / segments) and :meth:`split` (to
    produce output files).
    """

    @property
    @abstractmethod
    def supported_extensions(self) -> List[str]:
        """File extensions this plugin handles.

        Returns:
            List of extensions **including** the leading dot (e.g.
            ``[".xyz", ".abc"]``).
        """
        ...  # pragma: no cover

    @abstractmethod
    def detect(self, input_path: Path, **kwargs: Any) -> Any:
        """Detect segments / chapters in the file.

        Parameters:
            input_path: Path to the file to analyse.
            **kwargs: Detection options.

        Returns:
            A :class:`~lazy_splitter.core.models.DetectionResult` or
            compatible object.
        """
        ...  # pragma: no cover

    @abstractmethod
    def split(
        self,
        input_path: Path,
        segments: List[Any],
        **kwargs: Any,
    ) -> List[Path]:
        """Split the file according to the given segments.

        Parameters:
            input_path: Path to the source file.
            segments: Detected chapter / segment descriptors.
            **kwargs: Splitting options (output_dir, filename_pattern, etc.).

        Returns:
            List of :class:`~pathlib.Path` objects pointing to newly created
            files.
        """
        ...  # pragma: no cover


class OutputPlugin(Plugin):
    """Plugin that provides a custom output format.

    Subclasses expose :attr:`output_format` and implement :meth:`write` to
    serialise content into the custom format.
    """

    @property
    @abstractmethod
    def output_format(self) -> str:
        """Canonical name of the output format (e.g. ``"custom_pdf"``).

        Returns:
            Format identifier string.
        """
        ...  # pragma: no cover

    @abstractmethod
    def write(
        self,
        content: Any,
        output_path: Path,
        **kwargs: Any,
    ) -> Path:
        """Write *content* in this plugin's output format.

        Parameters:
            content: The data to serialise.  The exact type depends on the
                upstream pipeline (e.g. a list of page images, a chapter
                object, raw bytes, ...).
            output_path: Destination file path.
            **kwargs: Format-specific options.

        Returns:
            The path to the written file (usually the same as *output_path*).
        """
        ...  # pragma: no cover


class HookPlugin(Plugin):
    """Plugin that registers pre/post processing hooks.

    Instead of implementing detect / split / write, a :class:`HookPlugin`
    returns a mapping of event names to callback functions via
    :meth:`get_hooks`.  The :class:`~lazy_splitter.plugins.manager.PluginManager`
    feeds these into the :class:`~lazy_splitter.plugins.hooks.HookManager`
    automatically.

    Supported events:
        ``pre_detect``, ``post_detect``, ``pre_split``, ``post_split``,
        ``pre_merge``, ``post_merge``, ``on_error``.
    """

    def get_hooks(self) -> Dict[str, Callable[..., Any]]:
        """Return a mapping of event names to hook callables.

        Returns:
            Dictionary whose keys are event names (e.g. ``"pre_split"``)
            and whose values are callables accepting ``**kwargs``.
        """
        return {}


# ---------------------------------------------------------------------------
# Registration decorators
# ---------------------------------------------------------------------------

def register_strategy(name: str) -> Callable[[Type[Any]], Type[Any]]:
    """Decorator that registers a class as a detection strategy.

    The decorated class is stored in a global registry and will be picked
    up by :meth:`PluginManager.discover_plugins`.

    Parameters:
        name: Strategy identifier (e.g. ``"my_strategy"``).

    Returns:
        A class decorator.

    Usage::

        @register_strategy("my_custom")
        class MyDetector:
            def detect(self, input_path, **kwargs):
                ...
    """

    def decorator(cls: Type[Any]) -> Type[Any]:
        _STRATEGY_REGISTRY[name] = cls
        return cls

    return decorator


def register_file_handler(*extensions: str) -> Callable[[Type[Any]], Type[Any]]:
    """Decorator that registers a class as a file type handler.

    Parameters:
        *extensions: One or more file extensions including the leading dot
            (e.g. ``".xyz"``, ``".abc"``).

    Returns:
        A class decorator.

    Usage::

        @register_file_handler(".xyz", ".abc")
        class XyzHandler:
            def detect(self, input_path, **kwargs): ...
            def split(self, input_path, segments, **kwargs): ...
    """

    def decorator(cls: Type[Any]) -> Type[Any]:
        for ext in extensions:
            _FILE_HANDLER_REGISTRY[ext.lower()] = cls
        return cls

    return decorator


# ---------------------------------------------------------------------------
# Registry accessors (used internally by PluginManager)
# ---------------------------------------------------------------------------

def get_registered_strategies() -> Dict[str, Type[Any]]:
    """Return a copy of the decorator-populated strategy registry.

    Returns:
        Dictionary mapping strategy names to detector classes.
    """
    return dict(_STRATEGY_REGISTRY)


def get_registered_file_handlers() -> Dict[str, Type[Any]]:
    """Return a copy of the decorator-populated file handler registry.

    Returns:
        Dictionary mapping file extensions to handler classes.
    """
    return dict(_FILE_HANDLER_REGISTRY)
