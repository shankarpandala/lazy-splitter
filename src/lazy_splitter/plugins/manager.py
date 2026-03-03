"""Plugin manager for discovering, loading, and managing plugins.

The :class:`PluginManager` is the central coordinator for the plugin system.
It discovers installed plugins via :mod:`importlib.metadata` entry points,
loads them on demand, and maintains registries of strategies, file handlers,
and output formats contributed by plugins.

Entry point group: ``lazy_splitter.plugins``

Example ``pyproject.toml`` for a third-party plugin::

    [project.entry-points."lazy_splitter.plugins"]
    my_awesome_plugin = "my_package.plugin:AwesomePlugin"

Usage::

    from lazy_splitter.plugins.manager import PluginManager

    pm = PluginManager()
    discovered = pm.discover_plugins()

    for info in discovered:
        print(info.name, info.module)

    plugin = pm.load_plugin("my_awesome_plugin")
    strategies = pm.get_strategies()
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Dict, List, Optional, Type

from lazy_splitter.core.exceptions import PluginError
from lazy_splitter.plugins.base import (
    FileTypePlugin,
    HookPlugin,
    OutputPlugin,
    Plugin,
    StrategyPlugin,
    get_registered_file_handlers,
    get_registered_strategies,
)

logger = logging.getLogger(__name__)

#: Entry point group under which lazy-splitter plugins are registered.
ENTRY_POINT_GROUP: str = "lazy_splitter.plugins"


# ---------------------------------------------------------------------------
# PluginInfo
# ---------------------------------------------------------------------------

class PluginInfo:
    """Metadata about a discovered (but not necessarily loaded) plugin.

    Attributes:
        name: Entry point name.
        module: Dotted module path (possibly with ``:ClassName`` suffix).
        plugin_class: Resolved class (set after loading).
        is_loaded: Whether the plugin has been successfully loaded.
        instance: The live plugin instance (set after loading).
    """

    def __init__(
        self,
        name: str,
        module: str,
        plugin_class: Optional[Type[Plugin]] = None,
    ) -> None:
        self.name: str = name
        self.module: str = module
        self.plugin_class: Optional[Type[Plugin]] = plugin_class
        self.is_loaded: bool = False
        self.instance: Optional[Plugin] = None

    def __repr__(self) -> str:
        loaded = "loaded" if self.is_loaded else "not loaded"
        return f"PluginInfo(name={self.name!r}, module={self.module!r}, {loaded})"


# ---------------------------------------------------------------------------
# PluginManager
# ---------------------------------------------------------------------------

class PluginManager:
    """Discovers, loads, and manages lazy-splitter plugins.

    The manager maintains three registries that aggregate contributions from
    all loaded plugins:

    * **strategies** -- custom detection strategies.
    * **file_handlers** -- handlers for additional file types.
    * **output_formats** -- custom output format writers.

    Attributes:
        _plugins: Discovered plugin info objects keyed by name.
        _strategies: Registered detection strategy classes.
        _file_handlers: Registered file-type handler classes.
        _output_formats: Registered output format writer classes.
        _loaded: Already-loaded plugin instances keyed by name.
    """

    def __init__(self) -> None:
        self._plugins: Dict[str, PluginInfo] = {}
        self._strategies: Dict[str, Type[Any]] = {}
        self._file_handlers: Dict[str, Type[Any]] = {}
        self._output_formats: Dict[str, Type[Any]] = {}
        self._loaded: Dict[str, Plugin] = {}

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover_plugins(self) -> List[PluginInfo]:
        """Discover installed plugins via entry points.

        Scans the ``lazy_splitter.plugins`` entry point group for installed
        packages that provide plugins.  Also incorporates classes registered
        via the :func:`~lazy_splitter.plugins.base.register_strategy` and
        :func:`~lazy_splitter.plugins.base.register_file_handler` decorators.

        Returns:
            List of :class:`PluginInfo` objects for every discovered plugin.
        """
        discovered: List[PluginInfo] = []

        try:
            # Python 3.9+ ships importlib.metadata in the stdlib.  For 3.8
            # the ``importlib_metadata`` backport is tried as a fallback.
            try:
                from importlib.metadata import entry_points  # type: ignore[attr-defined]
            except ImportError:
                from importlib_metadata import entry_points  # type: ignore[no-redef]

            # Python 3.12+ returns a SelectableGroups object; older versions
            # require the *group* keyword argument or dict-style access.
            try:
                eps = entry_points(group=ENTRY_POINT_GROUP)
            except TypeError:
                all_eps = entry_points()
                eps = all_eps.get(ENTRY_POINT_GROUP, [])  # type: ignore[assignment]

            for ep in eps:
                info = PluginInfo(name=ep.name, module=ep.value)
                self._plugins[ep.name] = info
                discovered.append(info)
                logger.info("Discovered plugin: %s (%s)", ep.name, ep.value)

        except Exception as exc:
            logger.debug("Plugin discovery via entry points failed: %s", exc)

        # Merge decorator-registered strategies and file handlers.
        for name, cls in get_registered_strategies().items():
            if name not in self._strategies:
                self._strategies[name] = cls

        for ext, cls in get_registered_file_handlers().items():
            if ext not in self._file_handlers:
                self._file_handlers[ext] = cls

        return discovered

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_plugin(self, name: str) -> Plugin:
        """Load and activate a specific plugin by name.

        If the plugin has already been loaded, the cached instance is
        returned immediately.

        Parameters:
            name: Plugin name as declared in the entry point.

        Returns:
            The activated :class:`~lazy_splitter.plugins.base.Plugin`
            instance.

        Raises:
            PluginError: If the plugin is unknown or fails to load.
        """
        if name in self._loaded:
            return self._loaded[name]

        info = self._plugins.get(name)
        if info is None:
            raise PluginError(
                f"Plugin not found: {name!r}. "
                f"Available plugins: {sorted(self._plugins)}",
                plugin=name,
            )

        try:
            plugin_class = self._resolve_class(info.module)
            if plugin_class is None:
                raise PluginError(
                    f"No Plugin subclass found in {info.module!r}",
                    plugin=name,
                )

            instance = plugin_class()
            instance.activate()

            # Auto-register capabilities based on plugin type.
            if isinstance(instance, StrategyPlugin):
                self._strategies[instance.strategy_name] = type(instance)
            if isinstance(instance, FileTypePlugin):
                for ext in instance.supported_extensions:
                    self._file_handlers[ext.lower()] = type(instance)
            if isinstance(instance, OutputPlugin):
                self._output_formats[instance.output_format] = type(instance)
            # HookPlugin hooks are registered by the caller via HookManager.

            info.is_loaded = True
            info.instance = instance
            info.plugin_class = type(instance)
            self._loaded[name] = instance

            logger.info(
                "Loaded plugin: %s v%s (%s)",
                instance.name,
                instance.version,
                instance.description or "no description",
            )
            return instance

        except PluginError:
            raise
        except Exception as exc:
            raise PluginError(
                f"Failed to load plugin {name!r}: {exc}",
                plugin=name,
            ) from exc

    # ------------------------------------------------------------------
    # Runtime registration
    # ------------------------------------------------------------------

    def register_strategy(self, name: str, detector_class: Type[Any]) -> None:
        """Register a custom detection strategy at runtime.

        Parameters:
            name: Strategy name (used in ``--strategy`` CLI option).
            detector_class: Class implementing a ``detect(input_path, **kwargs)``
                method.
        """
        self._strategies[name] = detector_class
        logger.info("Registered strategy: %s -> %s", name, detector_class)

    def register_file_type(self, extension: str, handler_class: Type[Any]) -> None:
        """Register a custom file type handler at runtime.

        Parameters:
            extension: File extension including leading dot (e.g. ``".xyz"``).
            handler_class: Class implementing ``detect()`` and ``split()``.
        """
        self._file_handlers[extension.lower()] = handler_class
        logger.info("Registered file handler: %s -> %s", extension, handler_class)

    def register_output_format(self, name: str, writer_class: Type[Any]) -> None:
        """Register a custom output format at runtime.

        Parameters:
            name: Format name.
            writer_class: Class implementing
                ``write(content, output_path, **kwargs)``.
        """
        self._output_formats[name] = writer_class
        logger.info("Registered output format: %s -> %s", name, writer_class)

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_strategies(self) -> Dict[str, Type[Any]]:
        """Return all registered detection strategies.

        Returns:
            Dictionary mapping strategy names to detector classes.  Includes
            both built-in decorator-registered strategies and those
            contributed by loaded plugins.
        """
        return dict(self._strategies)

    def get_file_handlers(self) -> Dict[str, Type[Any]]:
        """Return all registered file type handlers.

        Returns:
            Dictionary mapping file extensions to handler classes.
        """
        return dict(self._file_handlers)

    def get_output_formats(self) -> Dict[str, Type[Any]]:
        """Return all registered output format writers.

        Returns:
            Dictionary mapping format names to writer classes.
        """
        return dict(self._output_formats)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def unload_all(self) -> None:
        """Deactivate and unload all loaded plugins.

        Each plugin's :meth:`~Plugin.deactivate` method is called.  Errors
        during deactivation are logged but do not prevent other plugins
        from being deactivated.
        """
        for name, plugin in self._loaded.items():
            try:
                plugin.deactivate()
                logger.info("Deactivated plugin: %s", name)
            except Exception as exc:
                logger.warning(
                    "Error deactivating plugin %s: %s", name, exc,
                )
        self._loaded.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_class(module_spec: str) -> Optional[Type[Plugin]]:
        """Import a module spec and return the plugin class.

        Parameters:
            module_spec: A string of the form ``"package.module:ClassName"``
                or ``"package.module"`` (in which case the first
                :class:`Plugin` subclass found in the module is used).

        Returns:
            The resolved :class:`Plugin` subclass, or ``None`` if none was
            found.
        """
        module_path, _, attr_name = module_spec.rpartition(":")
        if not module_path:
            # No colon -- the whole string is the module path.
            module_path = module_spec
            attr_name = ""

        module = importlib.import_module(module_path)

        if attr_name:
            cls = getattr(module, attr_name, None)
            if cls is not None and isinstance(cls, type) and issubclass(cls, Plugin):
                return cls
            return None

        # Search for the first Plugin subclass in the module.
        for name in dir(module):
            obj = getattr(module, name)
            if (
                isinstance(obj, type)
                and issubclass(obj, Plugin)
                and obj is not Plugin
                and obj not in (StrategyPlugin, FileTypePlugin, OutputPlugin, HookPlugin)
            ):
                return obj

        return None
