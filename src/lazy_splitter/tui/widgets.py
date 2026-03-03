"""Custom TUI widgets for lazy-splitter.

Provides reusable Textual widgets for chapter editing, file browsing,
split progress tracking, and format/strategy selection.

All imports from ``textual`` are guarded so that the module can be safely
imported when Textual is not installed -- only *instantiation* of the
widgets will fail with an actionable error.

Classes:
    ChapterTable: Editable chapter preview table.
    FileTree: File browser with type-based filtering.
    SplitProgress: Per-file split progress tracker.
    FormatSelector: Output format selection widget.
    StrategySelector: Detection strategy selector with descriptions.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set

from lazy_splitter.core.models import Chapter
from lazy_splitter.core.utils import format_duration, format_file_size
from lazy_splitter.tui import require_textual

# Guard all Textual imports behind a try/except so that importing this
# module never fails, even when Textual is absent.
try:
    from textual.app import ComposeResult
    from textual.containers import Container, Horizontal, Vertical
    from textual.message import Message
    from textual.reactive import reactive
    from textual.widget import Widget
    from textual.widgets import (
        Button,
        DataTable,
        Label,
        ListItem,
        ListView,
        ProgressBar,
        Static,
    )
except ImportError:  # pragma: no cover
    # Provide minimal stubs so the class bodies parse without error.
    # Actual instantiation is blocked by require_textual() in __init__.
    class _Stub:
        """Placeholder base that allows subclass definitions to succeed."""
        def __init_subclass__(cls, **kwargs: Any) -> None:
            super().__init_subclass__(**kwargs)

    Widget = _Stub  # type: ignore[misc,assignment]
    ComposeResult = Any  # type: ignore[misc,assignment]

    class Message:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass
        def __init_subclass__(cls, **kwargs: Any) -> None:
            super().__init_subclass__(**kwargs)

    class reactive:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass
        def __set_name__(self, owner: Any, name: str) -> None:
            pass
        def __get__(self, obj: Any, objtype: Any = None) -> Any:
            return None
        def __set__(self, obj: Any, value: Any) -> None:
            pass

    Container = _Stub  # type: ignore[misc,assignment]
    Horizontal = _Stub  # type: ignore[misc,assignment]
    Vertical = _Stub  # type: ignore[misc,assignment]
    Button = _Stub  # type: ignore[misc,assignment]
    DataTable = _Stub  # type: ignore[misc,assignment]
    Label = _Stub  # type: ignore[misc,assignment]
    ListItem = _Stub  # type: ignore[misc,assignment]
    ListView = _Stub  # type: ignore[misc,assignment]
    ProgressBar = _Stub  # type: ignore[misc,assignment]
    Static = _Stub  # type: ignore[misc,assignment]


# ---------------------------------------------------------------------------
# ChapterTable
# ---------------------------------------------------------------------------

class ChapterTable(Widget):
    """Editable chapter preview table.

    Extends :class:`~textual.widgets.DataTable` semantics to support
    renaming, reordering, and deleting chapters in-place.

    Attributes:
        chapters: Internal list of chapter data dictionaries.
    """

    DEFAULT_CSS = """
    ChapterTable {
        height: 1fr;
    }
    #chapter-dt {
        height: 1fr;
    }
    """

    class ChapterSelected(Message):
        """Posted when a chapter row is selected.

        Attributes:
            index: Zero-based chapter index.
            chapter: The selected chapter data dictionary.
        """

        def __init__(self, index: int, chapter: Dict[str, Any]) -> None:
            super().__init__()
            self.index = index
            self.chapter = chapter

    class ChaptersChanged(Message):
        """Posted when the chapter list is modified (add, delete, reorder)."""

        def __init__(self, chapters: List[Dict[str, Any]]) -> None:
            super().__init__()
            self.chapters = chapters

    def __init__(
        self,
        chapters: Optional[Sequence[Any]] = None,
        *,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ) -> None:
        require_textual()
        super().__init__(name=name, id=id, classes=classes)
        self._chapters: List[Dict[str, Any]] = []
        if chapters:
            self.load_chapters(chapters)

    def compose(self) -> ComposeResult:
        """Build the widget tree."""
        table = DataTable(id="chapter-dt")
        table.cursor_type = "row"
        yield table

    def on_mount(self) -> None:
        """Set up columns when the widget is first mounted."""
        table = self.query_one("#chapter-dt", DataTable)
        table.add_columns(
            "#", "Title", "Start", "End", "Pages", "Method", "Confidence",
        )
        self._refresh_rows()

    # -- Public API ----------------------------------------------------------

    def load_chapters(self, chapters: Sequence[Any]) -> None:
        """Replace the current chapter list with *chapters*.

        Parameters:
            chapters: Sequence of chapter / segment dataclass instances or
                plain dictionaries.
        """
        self._chapters.clear()
        for ch in chapters:
            if isinstance(ch, Chapter):
                self._chapters.append({
                    "title": ch.title,
                    "start": ch.start_page,
                    "end": ch.end_page,
                    "pages": ch.page_count,
                    "method": ch.detection_method,
                    "confidence": ch.confidence,
                })
            elif isinstance(ch, dict):
                self._chapters.append(ch)
            else:
                # Generic segment: pull common attributes
                self._chapters.append({
                    "title": getattr(ch, "title", str(ch)),
                    "start": getattr(ch, "start_page", getattr(ch, "start_time", "-")),
                    "end": getattr(ch, "end_page", getattr(ch, "end_time", "-")),
                    "pages": getattr(ch, "page_count", getattr(ch, "duration", "-")),
                    "method": getattr(ch, "detection_method", "-"),
                    "confidence": getattr(ch, "confidence", 1.0),
                })
        self._refresh_rows()

    def get_chapters(self) -> List[Dict[str, Any]]:
        """Return the current chapter list as dictionaries.

        Returns:
            List of chapter data dictionaries.
        """
        return list(self._chapters)

    def rename_chapter(self, index: int, new_title: str) -> None:
        """Rename the chapter at *index*.

        Parameters:
            index: Zero-based chapter index.
            new_title: New title string.
        """
        if 0 <= index < len(self._chapters):
            self._chapters[index]["title"] = new_title
            self._refresh_rows()
            self.post_message(self.ChaptersChanged(list(self._chapters)))

    def delete_chapter(self, index: int) -> None:
        """Remove the chapter at *index*.

        Parameters:
            index: Zero-based chapter index.
        """
        if 0 <= index < len(self._chapters):
            del self._chapters[index]
            self._refresh_rows()
            self.post_message(self.ChaptersChanged(list(self._chapters)))

    def move_chapter(self, from_index: int, to_index: int) -> None:
        """Move a chapter from *from_index* to *to_index*.

        Parameters:
            from_index: Current position (zero-based).
            to_index: Desired position (zero-based).
        """
        if (
            0 <= from_index < len(self._chapters)
            and 0 <= to_index < len(self._chapters)
        ):
            chapter = self._chapters.pop(from_index)
            self._chapters.insert(to_index, chapter)
            self._refresh_rows()
            self.post_message(self.ChaptersChanged(list(self._chapters)))

    # -- Internal helpers ----------------------------------------------------

    def _refresh_rows(self) -> None:
        """Clear and re-populate the data table from ``self._chapters``."""
        try:
            table = self.query_one("#chapter-dt", DataTable)
        except Exception:
            # Widget not yet mounted.
            return

        table.clear()
        for idx, ch in enumerate(self._chapters):
            confidence = ch.get("confidence", 1.0)
            conf_str = (
                f"{confidence:.0%}" if isinstance(confidence, (int, float)) else str(confidence)
            )
            table.add_row(
                str(idx + 1),
                str(ch.get("title", "")),
                str(ch.get("start", "-")),
                str(ch.get("end", "-")),
                str(ch.get("pages", "-")),
                str(ch.get("method", "-")),
                conf_str,
            )


# ---------------------------------------------------------------------------
# FileTree
# ---------------------------------------------------------------------------

class FileTree(Widget):
    """File browser widget with extension-based filtering.

    Displays a directory listing that can be filtered by file type and
    navigated with keyboard or mouse.

    Attributes:
        root_path: The base directory being browsed.
        filter_extensions: Set of allowed file extensions (empty = show all).
    """

    DEFAULT_CSS = """
    FileTree {
        height: 1fr;
    }
    #file-list {
        height: 1fr;
    }
    #file-tree-path {
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    """

    class FileSelected(Message):
        """Posted when a file is selected.

        Attributes:
            path: Absolute path to the selected file.
        """

        def __init__(self, path: str) -> None:
            super().__init__()
            self.path = path

    class DirectoryChanged(Message):
        """Posted when the current directory changes.

        Attributes:
            path: Absolute path to the new directory.
        """

        def __init__(self, path: str) -> None:
            super().__init__()
            self.path = path

    root_path: reactive[str] = reactive(".")
    filter_extensions: reactive[frozenset] = reactive(frozenset)

    def __init__(
        self,
        path: Optional[str] = None,
        filter_extensions: Optional[Set[str]] = None,
        *,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ) -> None:
        require_textual()
        super().__init__(name=name, id=id, classes=classes)
        self.root_path = path or str(Path.cwd())
        self.filter_extensions = frozenset(filter_extensions or set())

    def compose(self) -> ComposeResult:
        """Build the widget tree."""
        yield Label(self.root_path, id="file-tree-path")
        yield ListView(id="file-list")

    def on_mount(self) -> None:
        """Populate the list with directory contents."""
        self._refresh_listing()

    def watch_root_path(self, new_path: str) -> None:
        """React to changes of :attr:`root_path`."""
        try:
            path_label = self.query_one("#file-tree-path", Label)
            path_label.update(new_path)
        except Exception:
            pass
        self._refresh_listing()

    # -- Public API ----------------------------------------------------------

    def navigate_to(self, directory: str) -> None:
        """Change the current directory.

        Parameters:
            directory: Absolute path to navigate to.
        """
        target = Path(directory)
        if target.is_dir():
            self.root_path = str(target)
            self.post_message(self.DirectoryChanged(self.root_path))

    def set_filter(self, extensions: Set[str]) -> None:
        """Update the extension filter.

        Parameters:
            extensions: Set of extensions (including leading dot) to show.
                An empty set means show all files.
        """
        self.filter_extensions = frozenset(extensions)
        self._refresh_listing()

    # -- Internal helpers ----------------------------------------------------

    def _refresh_listing(self) -> None:
        """Re-populate the file list from the current :attr:`root_path`."""
        try:
            list_view = self.query_one("#file-list", ListView)
        except Exception:
            return

        list_view.clear()

        root = Path(self.root_path)
        if not root.is_dir():
            return

        # Parent directory entry
        parent = root.parent
        if parent != root:
            list_view.append(ListItem(Label(".. (parent)"), id="item-parent"))

        entries: List[Path] = []
        try:
            entries = sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            list_view.append(ListItem(Label("[permission denied]")))
            return

        for entry in entries:
            if entry.name.startswith("."):
                continue

            if entry.is_dir():
                label_text = f"[dir] {entry.name}/"
            else:
                if self.filter_extensions and entry.suffix.lower() not in self.filter_extensions:
                    continue
                try:
                    size = format_file_size(entry.stat().st_size)
                except OSError:
                    size = "?"
                label_text = f"      {entry.name}  ({size})"

            item_id = f"item-{entry.name}".replace(".", "-").replace(" ", "-")
            list_view.append(ListItem(Label(label_text), id=item_id))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle selection of a list item."""
        item = event.item
        label = item.query_one(Label)
        text = str(label.renderable).strip()

        if text == ".. (parent)":
            parent = str(Path(self.root_path).parent)
            self.navigate_to(parent)
            return

        if text.startswith("[dir]"):
            dir_name = text.replace("[dir]", "").strip().rstrip("/")
            target = str(Path(self.root_path) / dir_name)
            self.navigate_to(target)
            return

        # Regular file -- extract name (everything before the size in parens)
        file_name = text.strip()
        if "(" in file_name:
            file_name = file_name[: file_name.rfind("(")].strip()
        full_path = str(Path(self.root_path) / file_name)
        self.post_message(self.FileSelected(full_path))


# ---------------------------------------------------------------------------
# SplitProgress
# ---------------------------------------------------------------------------

class SplitProgress(Widget):
    """Split progress widget with per-file tracking.

    Displays an overall progress bar, a list of completed files, and
    the file currently being processed.
    """

    DEFAULT_CSS = """
    SplitProgress {
        height: auto;
        min-height: 8;
    }
    #sp-overall-label {
        text-align: center;
        margin: 1 0;
    }
    #sp-progress-bar {
        margin: 0 2;
    }
    #sp-current-label {
        text-align: center;
        margin: 1 0;
        color: $text-muted;
    }
    #sp-elapsed-label {
        text-align: center;
        color: $text-muted;
    }
    #sp-file-log {
        height: auto;
        max-height: 10;
        margin: 1 2;
        overflow-y: auto;
    }
    """

    class SplitComplete(Message):
        """Posted when all files have been processed."""
        pass

    total: reactive[int] = reactive(0)
    completed: reactive[int] = reactive(0)
    current_file: reactive[str] = reactive("")

    def __init__(
        self,
        total: int = 0,
        *,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ) -> None:
        require_textual()
        super().__init__(name=name, id=id, classes=classes)
        self.total = total
        self._start_time: float = time.monotonic()
        self._file_log: List[str] = []

    def compose(self) -> ComposeResult:
        """Build the widget tree."""
        yield Label("Preparing...", id="sp-overall-label")
        yield ProgressBar(total=100, id="sp-progress-bar")
        yield Label("", id="sp-current-label")
        yield Label("Elapsed: 0s", id="sp-elapsed-label")
        yield Static("", id="sp-file-log")

    # -- Public API ----------------------------------------------------------

    def start(self, total: int) -> None:
        """Begin tracking progress for *total* files.

        Parameters:
            total: Total number of files to process.
        """
        self.total = total
        self.completed = 0
        self.current_file = ""
        self._start_time = time.monotonic()
        self._file_log.clear()
        self._update_display()

    def advance(self, file_name: str = "") -> None:
        """Record completion of one file.

        Parameters:
            file_name: Name of the file that was just completed.
        """
        self.completed += 1
        if file_name:
            self._file_log.append(f"  [done] {file_name}")
        self._update_display()

        if self.completed >= self.total:
            self.post_message(self.SplitComplete())

    def set_current(self, file_name: str) -> None:
        """Update the label showing which file is being processed.

        Parameters:
            file_name: Name of the file currently in progress.
        """
        self.current_file = file_name
        self._update_display()

    # -- Internal helpers ----------------------------------------------------

    def _update_display(self) -> None:
        """Refresh all labels and the progress bar."""
        try:
            pct = (self.completed / self.total * 100) if self.total > 0 else 0

            overall = self.query_one("#sp-overall-label", Label)
            overall.update(f"Progress: {self.completed}/{self.total} ({pct:.0f}%)")

            bar = self.query_one("#sp-progress-bar", ProgressBar)
            bar.update(total=100, progress=pct)

            current = self.query_one("#sp-current-label", Label)
            if self.current_file:
                current.update(f"Processing: {self.current_file}")
            elif self.completed >= self.total and self.total > 0:
                current.update("Complete!")
            else:
                current.update("")

            elapsed = time.monotonic() - self._start_time
            elapsed_label = self.query_one("#sp-elapsed-label", Label)
            elapsed_label.update(f"Elapsed: {format_duration(elapsed)}")

            log_widget = self.query_one("#sp-file-log", Static)
            log_widget.update("\n".join(self._file_log[-10:]))
        except Exception:
            # Widget may not yet be mounted.
            pass


# ---------------------------------------------------------------------------
# FormatSelector
# ---------------------------------------------------------------------------

class FormatSelector(Widget):
    """Widget for selecting an output format.

    Displays available output formats as a selectable list with
    descriptions.
    """

    DEFAULT_CSS = """
    FormatSelector {
        height: auto;
        min-height: 5;
    }
    #format-title {
        padding: 0 1;
        text-style: bold;
    }
    #format-list {
        height: auto;
        max-height: 10;
    }
    """

    #: Default formats and their human-readable descriptions.
    DEFAULT_FORMATS: Dict[str, str] = {
        "pdf": "PDF -- Portable Document Format",
        "epub": "EPUB -- Electronic Publication",
        "mp3": "MP3 -- MPEG Audio Layer 3",
        "flac": "FLAC -- Free Lossless Audio Codec",
        "mp4": "MP4 -- MPEG-4 Video",
        "mkv": "MKV -- Matroska Video",
        "png": "PNG -- Portable Network Graphics",
        "docx": "DOCX -- Microsoft Word Document",
    }

    class FormatSelected(Message):
        """Posted when a format is chosen.

        Attributes:
            format_name: The selected format identifier (e.g. ``"pdf"``).
        """

        def __init__(self, format_name: str) -> None:
            super().__init__()
            self.format_name = format_name

    selected_format: reactive[str] = reactive("")

    def __init__(
        self,
        formats: Optional[Dict[str, str]] = None,
        *,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ) -> None:
        require_textual()
        super().__init__(name=name, id=id, classes=classes)
        self._formats: Dict[str, str] = formats or dict(self.DEFAULT_FORMATS)

    def compose(self) -> ComposeResult:
        """Build the widget tree."""
        yield Label("Output Format", id="format-title")
        yield ListView(id="format-list")

    def on_mount(self) -> None:
        """Populate the format list."""
        list_view = self.query_one("#format-list", ListView)
        for fmt_name, description in self._formats.items():
            item_id = f"fmt-{fmt_name}"
            list_view.append(ListItem(Label(f"{fmt_name:6s}  {description}"), id=item_id))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle format selection."""
        item = event.item
        label = item.query_one(Label)
        text = str(label.renderable).strip()
        # Extract format name (first word).
        fmt_name = text.split()[0] if text else ""
        self.selected_format = fmt_name
        self.post_message(self.FormatSelected(fmt_name))

    # -- Public API ----------------------------------------------------------

    def set_formats(self, formats: Dict[str, str]) -> None:
        """Replace available formats.

        Parameters:
            formats: Mapping of format name to human-readable description.
        """
        self._formats = dict(formats)
        try:
            list_view = self.query_one("#format-list", ListView)
            list_view.clear()
            for fmt_name, description in self._formats.items():
                item_id = f"fmt-{fmt_name}"
                list_view.append(
                    ListItem(Label(f"{fmt_name:6s}  {description}"), id=item_id)
                )
        except Exception:
            pass

    def get_selected(self) -> str:
        """Return the currently selected format name.

        Returns:
            Format identifier string, or ``""`` if none is selected.
        """
        return self.selected_format


# ---------------------------------------------------------------------------
# StrategySelector
# ---------------------------------------------------------------------------

class StrategySelector(Widget):
    """Widget for selecting a chapter detection strategy.

    Displays strategies with short descriptions so the user can make an
    informed choice.
    """

    DEFAULT_CSS = """
    StrategySelector {
        height: auto;
        min-height: 5;
    }
    #strategy-title {
        padding: 0 1;
        text-style: bold;
    }
    #strategy-list {
        height: auto;
        max-height: 12;
    }
    """

    #: Built-in strategies and their descriptions.
    DEFAULT_STRATEGIES: Dict[str, str] = {
        "auto": "Automatically select the best strategy for the file type.",
        "bookmarks": "Use PDF bookmarks / table of contents entries.",
        "toc": "Parse an embedded table of contents.",
        "heuristic": "Detect chapters using heading patterns and page layout.",
        "hybrid": "Combine multiple strategies and pick the best result.",
        "silence": "Detect silence-based chapter boundaries (audio/video).",
        "scene": "Detect scene changes via visual analysis (video).",
        "regex": "Match chapter headings with user-supplied regex patterns.",
    }

    class StrategySelected(Message):
        """Posted when a strategy is chosen.

        Attributes:
            strategy_name: The selected strategy identifier.
            description: Human-readable description of the strategy.
        """

        def __init__(self, strategy_name: str, description: str) -> None:
            super().__init__()
            self.strategy_name = strategy_name
            self.description = description

    selected_strategy: reactive[str] = reactive("auto")

    def __init__(
        self,
        strategies: Optional[Dict[str, str]] = None,
        *,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ) -> None:
        require_textual()
        super().__init__(name=name, id=id, classes=classes)
        self._strategies: Dict[str, str] = strategies or dict(self.DEFAULT_STRATEGIES)

    def compose(self) -> ComposeResult:
        """Build the widget tree."""
        yield Label("Detection Strategy", id="strategy-title")
        yield ListView(id="strategy-list")

    def on_mount(self) -> None:
        """Populate the strategy list."""
        list_view = self.query_one("#strategy-list", ListView)
        for name, description in self._strategies.items():
            item_id = f"strat-{name}"
            list_view.append(
                ListItem(Label(f"{name:12s}  {description}"), id=item_id)
            )

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle strategy selection."""
        item = event.item
        label = item.query_one(Label)
        text = str(label.renderable).strip()
        # Extract strategy name (first word).
        strat_name = text.split()[0] if text else ""
        self.selected_strategy = strat_name
        description = self._strategies.get(strat_name, "")
        self.post_message(self.StrategySelected(strat_name, description))

    # -- Public API ----------------------------------------------------------

    def set_strategies(self, strategies: Dict[str, str]) -> None:
        """Replace available strategies.

        Parameters:
            strategies: Mapping of strategy name to description.
        """
        self._strategies = dict(strategies)
        try:
            list_view = self.query_one("#strategy-list", ListView)
            list_view.clear()
            for name, description in self._strategies.items():
                item_id = f"strat-{name}"
                list_view.append(
                    ListItem(Label(f"{name:12s}  {description}"), id=item_id)
                )
        except Exception:
            pass

    def get_selected(self) -> str:
        """Return the currently selected strategy name.

        Returns:
            Strategy identifier string.
        """
        return self.selected_strategy
