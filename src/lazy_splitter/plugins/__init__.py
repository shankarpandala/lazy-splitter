"""Plugin system for lazy-splitter.

This package provides an extensible plugin architecture that allows
third-party packages to register custom detection strategies, file type
handlers, output formats, and processing hooks.

Plugins are discovered via :mod:`importlib.metadata` entry points under the
``lazy_splitter.plugins`` group.  A plugin package simply needs to declare
the entry point in its ``pyproject.toml``::

    [project.entry-points."lazy_splitter.plugins"]
    my_plugin = "my_package.plugin:MyPlugin"

Quick start::

    from lazy_splitter.plugins.manager import PluginManager

    pm = PluginManager()
    pm.discover_plugins()

    # Registered strategies are now available for detection
    strategies = pm.get_strategies()

Sub-modules:
    base: Abstract base classes and registration decorators.
    manager: Plugin discovery, loading, and registry.
    hooks: Event hook system for pre/post processing callbacks.
"""

from __future__ import annotations

from lazy_splitter.plugins.base import (
    FileTypePlugin,
    HookPlugin,
    OutputPlugin,
    Plugin,
    StrategyPlugin,
    register_file_handler,
    register_strategy,
)
from lazy_splitter.plugins.hooks import HookManager, get_hook_manager
from lazy_splitter.plugins.manager import PluginInfo, PluginManager

__all__ = [
    "FileTypePlugin",
    "HookManager",
    "HookPlugin",
    "OutputPlugin",
    "Plugin",
    "PluginInfo",
    "PluginManager",
    "StrategyPlugin",
    "get_hook_manager",
    "register_file_handler",
    "register_strategy",
]
