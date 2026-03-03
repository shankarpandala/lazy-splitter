"""Configuration management for lazy-splitter.

Provides a :class:`LazyConfig` dataclass and helpers to load / save / merge
configuration from TOML files and CLI arguments.

Configuration is searched in this order (first match wins):

1. Explicit *path* argument passed to :func:`load_config`.
2. ``.lazy-splitter.toml`` in the current working directory.
3. ``~/.lazy-splitter.toml`` in the user's home directory.

If no file is found, sensible defaults are used.

.. note::

   Python 3.8 / 3.9 / 3.10 do not ship :mod:`tomllib` in the standard
   library so we fall back to a minimal hand-rolled TOML reader that covers
   the subset of TOML we actually use (flat key/value pairs and ``[section]``
   tables).  For richer TOML files you should install the ``tomli`` package.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from lazy_splitter.core.exceptions import ConfigError

# ---------------------------------------------------------------------------
# TOML helpers (works without third-party packages on Python 3.8+)
# ---------------------------------------------------------------------------


def _load_toml(path: Path) -> Dict[str, Any]:
    """Load a TOML file and return a nested dictionary.

    Tries :mod:`tomllib` (3.11+), then ``tomli``, then a minimal built-in
    parser that supports the subset of TOML we use.
    """
    text = path.read_text(encoding="utf-8")

    # Try stdlib first (Python >= 3.11)
    try:
        import tomllib  # type: ignore[import-not-found]
        return tomllib.loads(text)
    except ImportError:
        pass

    # Try the backport
    try:
        import tomli  # type: ignore[import-not-found]
        return tomli.loads(text)
    except ImportError:
        pass

    # Minimal fallback parser
    return _parse_toml_minimal(text)


def _parse_toml_minimal(text: str) -> Dict[str, Any]:
    """Minimal TOML parser covering flat tables and basic value types.

    This is *not* a fully-compliant TOML parser.  It handles:

    * ``[section]`` and ``[section.subsection]`` headers
    * String values (``"..."``)
    * Integer and float values
    * Boolean values (``true`` / ``false``)
    * Comments (``#``)

    Anything more exotic should use a proper library.
    """
    data: Dict[str, Any] = {}
    current_section: Optional[str] = None

    for raw_line in text.splitlines():
        line = raw_line.strip()

        # Skip blanks and comments
        if not line or line.startswith("#"):
            continue

        # Section header
        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1].strip()
            # Ensure nested dict exists
            parts = current_section.split(".")
            node = data
            for part in parts:
                node = node.setdefault(part, {})
            continue

        # Key = value
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()

            # Remove inline comments (only outside of strings)
            if value and value[0] not in ('"', "'"):
                comment_idx = value.find("#")
                if comment_idx != -1:
                    value = value[:comment_idx].strip()

            parsed = _parse_value(value)

            if current_section:
                parts = current_section.split(".")
                node = data
                for part in parts:
                    node = node.setdefault(part, {})
                node[key] = parsed
            else:
                data[key] = parsed

    return data


def _parse_value(value: str) -> Any:
    """Parse a single TOML value string into a Python object."""
    if not value:
        return ""

    # Quoted string
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]

    # Booleans
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False

    # Numbers
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        pass

    return value


def _dump_toml(data: Dict[str, Any]) -> str:
    """Serialise a (possibly nested) dictionary as minimal TOML text."""
    lines: List[str] = []
    top_level: Dict[str, Any] = {}
    sections: Dict[str, Dict[str, Any]] = {}

    for key, value in data.items():
        if isinstance(value, dict):
            sections[key] = value
        else:
            top_level[key] = value

    # Top-level keys first
    for key, value in top_level.items():
        lines.append(f"{key} = {_format_value(value)}")

    if top_level and sections:
        lines.append("")

    # Sections
    for section_name, section_data in sections.items():
        lines.append(f"[{section_name}]")
        for key, value in section_data.items():
            if isinstance(value, dict):
                # Subsections
                lines.append("")
                lines.append(f"[{section_name}.{key}]")
                for sub_key, sub_value in value.items():
                    lines.append(f"{sub_key} = {_format_value(sub_value)}")
            else:
                lines.append(f"{key} = {_format_value(value)}")
        lines.append("")

    return "\n".join(lines) + "\n"


def _format_value(value: Any) -> str:
    """Format a Python value as a TOML value string."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, str):
        # Escape backslashes and quotes
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return f'"{value}"'


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------

@dataclass
class LazyConfig:
    """Central configuration for lazy-splitter.

    Instances can be created directly, loaded from a TOML file via
    :func:`load_config`, or built by merging a file config with CLI overrides
    via :func:`merge_config`.

    Attributes:
        output_dir: Default directory for output files.  ``None`` means "same
            directory as the input file".
        filename_pattern: Pattern for naming output files.  Supports
            ``{title}``, ``{index}``, ``{ext}`` placeholders.
        strategy: Default detection strategy (``"auto"``, ``"bookmarks"``,
            ``"heuristic"``, ``"hybrid"``, etc.).
        sensitivity: Detection sensitivity (``"low"``, ``"medium"``, ``"high"``).
        verbose: Whether to enable verbose / debug output.
        dry_run: When ``True``, preview operations without writing files.
        json_output: When ``True``, emit machine-readable JSON instead of
            human-readable text.
        no_color: Disable colour / rich output.
        parallel_workers: Number of parallel workers for batch operations.
            ``0`` means auto-detect based on CPU count.
        profiles: Named configuration profiles that can override any of the
            above fields.
    """

    output_dir: Optional[str] = None
    filename_pattern: str = "{index:03d}_{title}{ext}"
    strategy: str = "auto"
    sensitivity: str = "medium"
    verbose: bool = False
    dry_run: bool = False
    json_output: bool = False
    no_color: bool = False
    parallel_workers: int = 0
    profiles: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the configuration to a plain dictionary.

        Returns:
            Dictionary representation, suitable for TOML serialisation.
        """
        result: Dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if f.name == "profiles" and value:
                result["profiles"] = dict(value)
            elif f.name != "profiles":
                result[f.name] = value
        return result


# ---------------------------------------------------------------------------
# Search paths
# ---------------------------------------------------------------------------

_DEFAULT_FILENAMES: List[str] = [
    ".lazy-splitter.toml",
]

_HOME_FILENAME: str = ".lazy-splitter.toml"


def _find_config_file() -> Optional[Path]:
    """Search for a configuration file in standard locations.

    Returns:
        The first configuration file found, or ``None``.
    """
    # Current directory
    cwd = Path.cwd()
    for name in _DEFAULT_FILENAMES:
        candidate = cwd / name
        if candidate.is_file():
            return candidate

    # Home directory
    home = Path.home()
    candidate = home / _HOME_FILENAME
    if candidate.is_file():
        return candidate

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_config(path: Optional[Union[str, Path]] = None) -> LazyConfig:
    """Load configuration from a TOML file.

    Parameters:
        path: Explicit path to the configuration file.  When ``None``, the
            standard search locations are checked.

    Returns:
        A populated :class:`LazyConfig` instance.  If no file is found the
        default configuration is returned.

    Raises:
        ConfigError: If the file exists but cannot be parsed.
    """
    if path is not None:
        config_path = Path(path)
        if not config_path.is_file():
            raise ConfigError(
                f"Configuration file not found: {config_path}",
                path=str(config_path),
            )
    else:
        config_path = _find_config_file()

    if config_path is None:
        return LazyConfig()

    try:
        data = _load_toml(config_path)
    except Exception as exc:
        raise ConfigError(
            f"Failed to parse configuration file: {config_path}",
            path=str(config_path),
            detail=str(exc),
        ) from exc

    return _dict_to_config(data)


def save_config(config: LazyConfig, path: Union[str, Path]) -> None:
    """Save configuration to a TOML file.

    Parameters:
        config: The configuration to persist.
        path: Destination file path.

    Raises:
        ConfigError: If the file cannot be written.
    """
    dest = Path(path)
    data = config.to_dict()

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(_dump_toml(data), encoding="utf-8")
    except OSError as exc:
        raise ConfigError(
            f"Failed to write configuration file: {dest}",
            path=str(dest),
            detail=str(exc),
        ) from exc


def get_profile(name: str, config: Optional[LazyConfig] = None) -> Dict[str, Any]:
    """Retrieve a named profile from the configuration.

    Parameters:
        name: Profile name.
        config: Configuration to search.  When ``None``, a fresh config is
            loaded via :func:`load_config`.

    Returns:
        A dictionary of profile overrides.

    Raises:
        ConfigError: If the profile does not exist.
    """
    if config is None:
        config = load_config()

    if name not in config.profiles:
        available = sorted(config.profiles.keys()) if config.profiles else []
        raise ConfigError(
            f"Profile {name!r} not found. Available profiles: {available}",
            profile=name,
        )

    return dict(config.profiles[name])


def merge_config(
    file_config: LazyConfig,
    cli_args: Dict[str, Any],
) -> LazyConfig:
    """Merge a file-based configuration with CLI argument overrides.

    CLI arguments take precedence over file-based values.  Keys in *cli_args*
    whose values are ``None`` are treated as "not provided" and are skipped.

    Parameters:
        file_config: Base configuration loaded from a file.
        cli_args: Dictionary of CLI argument names to values.

    Returns:
        A new :class:`LazyConfig` with merged values.
    """
    merged = file_config.to_dict()

    valid_keys = {f.name for f in fields(LazyConfig)}

    for key, value in cli_args.items():
        if value is None:
            continue
        if key in valid_keys:
            merged[key] = value

    return _dict_to_config(merged)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _dict_to_config(data: Dict[str, Any]) -> LazyConfig:
    """Build a :class:`LazyConfig` from a dictionary, ignoring unknown keys."""
    valid_keys = {f.name for f in fields(LazyConfig)}
    filtered = {k: v for k, v in data.items() if k in valid_keys}
    return LazyConfig(**filtered)
