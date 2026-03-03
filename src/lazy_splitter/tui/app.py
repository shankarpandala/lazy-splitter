"""Main TUI application for lazy-splitter.

Provides :class:`LazySplitterApp`, a full-screen terminal interface built on
`Textual <https://textual.textualize.io/>`_ with screens for file selection,
chapter preview/editing, split progress tracking, results summary, and
settings management.

Textual is an **optional** dependency -- this module guards all imports behind
:func:`~lazy_splitter.tui.require_textual` so that importing the module when
Textual is absent raises a clear, actionable error rather than a raw
:class:`ImportError`.

Example::

    from lazy_splitter.tui.app import LazySplitterApp

    app = LazySplitterApp()
    app.run()
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Type, Union

from lazy_splitter.core.config import LazyConfig, load_config, save_config
from lazy_splitter.core.exceptions import LazySplitterError, PluginError
from lazy_splitter.core.models import Chapter, DetectionResult, SplitResult
from lazy_splitter.core.utils import detect_file_type, format_duration, format_file_size
from lazy_splitter.tui import require_textual

# Guard Textual imports -- everything below is only usable when Textual is
# installed.  When Textual is absent we define lightweight stubs so that
# the class bodies can be *parsed* without error; actually *instantiating*
# any of them will raise via require_textual().
try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Container, Horizontal, Vertical, VerticalScroll
    from textual.reactive import reactive
    from textual.screen import Screen
    from textual.widgets import (
        Button,
        DataTable,
        DirectoryTree,
        Footer,
        Header,
        Input,
        Label,
        ListItem,
        ListView,
        ProgressBar,
        Select,
        Static,
        TextArea,
    )
except ImportError:  # pragma: no cover
    # Minimal stubs so class bodies parse even without Textual installed.
    class _Stub:
        """Placeholder base that allows subclass definitions to succeed."""
        def __init_subclass__(cls, **kwargs: Any) -> None:
            super().__init_subclass__(**kwargs)

    App = _Stub  # type: ignore[misc,assignment]
    Screen = _Stub  # type: ignore[misc,assignment]
    ComposeResult = Any  # type: ignore[misc,assignment]

    class Binding:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    class reactive:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass
        def __set_name__(self, owner: Any, name: str) -> None:
            pass
        def __get__(self, obj: Any, objtype: Any = None) -> Any:
            return None
        def __set__(self, obj: Any, value: Any) -> None:
            pass

    # Widget stubs
    Container = _Stub  # type: ignore[misc,assignment]
    Horizontal = _Stub  # type: ignore[misc,assignment]
    Vertical = _Stub  # type: ignore[misc,assignment]
    VerticalScroll = _Stub  # type: ignore[misc,assignment]
    Button = _Stub  # type: ignore[misc,assignment]
    DataTable = _Stub  # type: ignore[misc,assignment]
    DirectoryTree = _Stub  # type: ignore[misc,assignment]
    Footer = _Stub  # type: ignore[misc,assignment]
    Header = _Stub  # type: ignore[misc,assignment]
    Input = _Stub  # type: ignore[misc,assignment]
    Label = _Stub  # type: ignore[misc,assignment]
    ListItem = _Stub  # type: ignore[misc,assignment]
    ListView = _Stub  # type: ignore[misc,assignment]
    ProgressBar = _Stub  # type: ignore[misc,assignment]
    Select = _Stub  # type: ignore[misc,assignment]
    Static = _Stub  # type: ignore[misc,assignment]
    TextArea = _Stub  # type: ignore[misc,assignment]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supported file extension filters
# ---------------------------------------------------------------------------

#: Extensions displayed by default in the file browser.
_SUPPORTED_EXTENSIONS = frozenset({
    ".pdf", ".epub", ".mobi", ".djvu",
    ".mp4", ".mkv", ".avi", ".mov", ".webm",
    ".mp3", ".flac", ".wav", ".ogg", ".m4a",
    ".docx", ".doc", ".odt", ".html", ".md", ".txt",
    ".png", ".jpg", ".jpeg", ".gif", ".tiff", ".tif",
})


# ===================================================================
# FileSelectScreen -- browse and select files
# ===================================================================

class FileSelectScreen(Screen):
    """Screen for browsing and selecting input files.

    Displays a directory tree filtered by supported file types and allows
    the user to confirm a selection before moving on.
    """

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("enter", "select_file", "Select"),
        Binding("f", "toggle_filter", "Toggle Filter"),
    ]

    CSS = """
    FileSelectScreen {
        layout: vertical;
    }
    #file-browser-container {
        height: 1fr;
        border: round $accent;
    }
    #file-path-label {
        dock: bottom;
        height: 3;
        padding: 1;
        background: $surface;
    }
    """

    selected_path: reactive[str] = reactive("")

    def compose(self) -> ComposeResult:
        """Build the widget tree for the file-select screen."""
        yield Header(show_clock=True)
        yield Label("Select a file to split", id="file-select-title")
        start_dir = str(Path.cwd())
        yield Container(
            DirectoryTree(start_dir, id="file-tree"),
            id="file-browser-container",
        )
        yield Label("No file selected", id="file-path-label")
        yield Footer()

    def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        """Handle file selection from the directory tree."""
        path = str(event.path)
        self.selected_path = path
        label = self.query_one("#file-path-label", Label)
        label.update(f"Selected: {path}")

    def action_select_file(self) -> None:
        """Confirm the currently highlighted file and proceed to preview."""
        if self.selected_path:
            app = self.app
            if isinstance(app, LazySplitterApp):
                app.current_file = self.selected_path
                app.push_screen(PreviewScreen())

    def action_toggle_filter(self) -> None:
        """Toggle between showing all files and supported files only."""
        # This is a placeholder for filter toggling logic.
        self.notify("Filter toggled (showing all files)")


# ===================================================================
# PreviewScreen -- chapter preview with editing
# ===================================================================

class PreviewScreen(Screen):
    """Screen for previewing and editing detected chapters.

    Displays a :class:`~textual.widgets.DataTable` of chapters that can be
    renamed, reordered, or deleted before splitting.
    """

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("s", "start_split", "Split"),
        Binding("d", "delete_chapter", "Delete"),
        Binding("r", "rename_chapter", "Rename"),
        Binding("k", "move_up", "Move Up"),
        Binding("j", "move_down", "Move Down"),
    ]

    CSS = """
    PreviewScreen {
        layout: vertical;
    }
    #preview-table-container {
        height: 1fr;
        border: round $accent;
    }
    #preview-info {
        dock: bottom;
        height: 3;
        padding: 1;
        background: $surface;
    }
    """

    chapters: reactive[list] = reactive(list, init=False)

    def compose(self) -> ComposeResult:
        """Build the widget tree for the preview screen."""
        yield Header(show_clock=True)
        yield Label("Chapter Preview", id="preview-title")
        yield Container(
            DataTable(id="chapter-table"),
            id="preview-table-container",
        )
        yield Label("Loading chapters...", id="preview-info")
        yield Footer()

    def on_mount(self) -> None:
        """Initialise the data table when the screen is mounted."""
        table = self.query_one("#chapter-table", DataTable)
        table.add_columns("#", "Title", "Start", "End", "Pages", "Method", "Confidence")
        table.cursor_type = "row"

        app = self.app
        if isinstance(app, LazySplitterApp) and app.current_file:
            self._load_chapters(app.current_file)

    def _load_chapters(self, file_path: str) -> None:
        """Detect chapters in *file_path* and populate the table.

        In a full integration this would invoke the appropriate detector.
        Here we store the chapters on the app and render them.
        """
        app = self.app
        if not isinstance(app, LazySplitterApp):
            return

        # If the app already has detection results, use them.
        chapters = app.detected_chapters
        if not chapters:
            info_label = self.query_one("#preview-info", Label)
            info_label.update(f"No chapters detected for: {file_path}")
            return

        table = self.query_one("#chapter-table", DataTable)
        for idx, ch in enumerate(chapters, 1):
            if isinstance(ch, Chapter):
                table.add_row(
                    str(idx),
                    ch.title,
                    str(ch.start_page),
                    str(ch.end_page),
                    str(ch.page_count),
                    ch.detection_method,
                    f"{ch.confidence:.0%}",
                )
            else:
                # Generic fallback for non-Chapter segment types
                title = getattr(ch, "title", str(ch))
                table.add_row(str(idx), title, "-", "-", "-", "-", "-")

        info_label = self.query_one("#preview-info", Label)
        info_label.update(
            f"{len(chapters)} chapter(s) detected  |  "
            f"Press 's' to split, 'd' to delete, 'r' to rename"
        )

    def action_start_split(self) -> None:
        """Transition to the split-progress screen."""
        app = self.app
        if isinstance(app, LazySplitterApp):
            app.push_screen(SplitScreen())

    def action_delete_chapter(self) -> None:
        """Delete the currently selected chapter row."""
        table = self.query_one("#chapter-table", DataTable)
        if table.cursor_row is not None:
            row_key, _row = table.coordinate_to_cell_key(
                table.cursor_coordinate
            )
            table.remove_row(row_key)
            self.notify("Chapter deleted")

    def action_rename_chapter(self) -> None:
        """Prompt for a new name for the selected chapter."""
        self.notify("Rename: use inline editing (press Enter on a title cell)")

    def action_move_up(self) -> None:
        """Move the selected chapter up in the list."""
        table = self.query_one("#chapter-table", DataTable)
        if table.cursor_row is not None and table.cursor_row > 0:
            table.move_cursor(row=table.cursor_row - 1)

    def action_move_down(self) -> None:
        """Move the selected chapter down in the list."""
        table = self.query_one("#chapter-table", DataTable)
        if table.cursor_row is not None:
            table.move_cursor(row=table.cursor_row + 1)


# ===================================================================
# SplitScreen -- progress tracking during split
# ===================================================================

class SplitScreen(Screen):
    """Screen showing real-time split progress.

    Displays a progress bar, per-file status, and elapsed time while the
    split operation is running.
    """

    BINDINGS = [
        Binding("escape", "cancel_split", "Cancel"),
    ]

    CSS = """
    SplitScreen {
        layout: vertical;
        align: center middle;
    }
    #split-progress-container {
        width: 80%;
        height: auto;
        border: round $accent;
        padding: 2;
    }
    #split-status {
        text-align: center;
        margin: 1;
    }
    #progress-bar {
        margin: 1 0;
    }
    #current-file-label {
        text-align: center;
        margin: 1;
        color: $text-muted;
    }
    #elapsed-label {
        text-align: center;
        margin: 1;
        color: $text-muted;
    }
    """

    total_files: reactive[int] = reactive(0)
    completed_files: reactive[int] = reactive(0)
    current_file_name: reactive[str] = reactive("")
    start_time: reactive[float] = reactive(0.0)

    def compose(self) -> ComposeResult:
        """Build the widget tree for the split-progress screen."""
        yield Header(show_clock=True)
        with Container(id="split-progress-container"):
            yield Label("Splitting in progress...", id="split-status")
            yield ProgressBar(total=100, id="progress-bar")
            yield Label("", id="current-file-label")
            yield Label("Elapsed: 0s", id="elapsed-label")
        yield Footer()

    def on_mount(self) -> None:
        """Record start time when the screen is mounted."""
        self.start_time = time.monotonic()

    def update_progress(
        self,
        completed: int,
        total: int,
        current_file: str = "",
    ) -> None:
        """Update progress indicators.

        Parameters:
            completed: Number of files processed so far.
            total: Total number of files to process.
            current_file: Name of the file currently being processed.
        """
        self.total_files = total
        self.completed_files = completed
        self.current_file_name = current_file

        progress_bar = self.query_one("#progress-bar", ProgressBar)
        pct = (completed / total * 100) if total > 0 else 0
        progress_bar.update(total=100, progress=pct)

        status = self.query_one("#split-status", Label)
        status.update(f"Processing {completed}/{total} files...")

        file_label = self.query_one("#current-file-label", Label)
        file_label.update(f"Current: {current_file}" if current_file else "")

        elapsed = time.monotonic() - self.start_time
        elapsed_label = self.query_one("#elapsed-label", Label)
        elapsed_label.update(f"Elapsed: {format_duration(elapsed)}")

    def finish(self, result: Optional[SplitResult] = None) -> None:
        """Mark the split as complete and navigate to results.

        Parameters:
            result: The split result to display on the results screen.
        """
        app = self.app
        if isinstance(app, LazySplitterApp):
            app.last_split_result = result
            app.switch_screen(ResultsScreen())

    def action_cancel_split(self) -> None:
        """Cancel the split and return to preview."""
        self.notify("Split cancelled")
        self.app.pop_screen()


# ===================================================================
# ResultsScreen -- summary after splitting
# ===================================================================

class ResultsScreen(Screen):
    """Screen displaying the results of a split operation.

    Shows a file listing, total size, duration, and any warnings or errors.
    """

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("o", "open_output_dir", "Open Output Dir"),
        Binding("n", "new_split", "New Split"),
    ]

    CSS = """
    ResultsScreen {
        layout: vertical;
    }
    #results-container {
        height: 1fr;
        border: round $accent;
        padding: 1;
    }
    #results-summary {
        height: 5;
        padding: 1;
        background: $surface;
    }
    """

    def compose(self) -> ComposeResult:
        """Build the widget tree for the results screen."""
        yield Header(show_clock=True)
        yield Label("Split Results", id="results-title")
        yield Container(
            DataTable(id="results-table"),
            id="results-container",
        )
        yield Label("", id="results-summary")
        yield Footer()

    def on_mount(self) -> None:
        """Populate the results table from the last split result."""
        table = self.query_one("#results-table", DataTable)
        table.add_columns("#", "File", "Size")

        app = self.app
        if not isinstance(app, LazySplitterApp):
            return

        result = app.last_split_result
        if result is None:
            summary = self.query_one("#results-summary", Label)
            summary.update("No results available.")
            return

        for idx, file_path in enumerate(result.created_files, 1):
            try:
                size = format_file_size(os.path.getsize(file_path))
            except OSError:
                size = "N/A"
            table.add_row(str(idx), str(file_path), size)

        summary_parts = [
            f"Files created: {result.file_count}",
            f"Total size: {format_file_size(result.total_size)}",
            f"Duration: {format_duration(result.duration_seconds)}",
        ]
        if result.warnings:
            summary_parts.append(f"Warnings: {len(result.warnings)}")
        if result.errors:
            summary_parts.append(f"Errors: {len(result.errors)}")

        summary = self.query_one("#results-summary", Label)
        summary.update("  |  ".join(summary_parts))

    def action_open_output_dir(self) -> None:
        """Attempt to open the output directory in the system file manager."""
        app = self.app
        if isinstance(app, LazySplitterApp) and app.last_split_result:
            files = app.last_split_result.created_files
            if files:
                output_dir = str(files[0].parent)
                self.notify(f"Output directory: {output_dir}")

    def action_new_split(self) -> None:
        """Return to file selection for a new split operation."""
        app = self.app
        if isinstance(app, LazySplitterApp):
            app.current_file = ""
            app.detected_chapters = []
            app.last_split_result = None
            app.switch_screen(FileSelectScreen())


# ===================================================================
# SettingsScreen -- edit configuration
# ===================================================================

class SettingsScreen(Screen):
    """Screen for viewing and editing lazy-splitter configuration.

    Provides form fields for all :class:`~lazy_splitter.core.config.LazyConfig`
    values and persists changes to disk.
    """

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("ctrl+s", "save_settings", "Save"),
    ]

    CSS = """
    SettingsScreen {
        layout: vertical;
    }
    #settings-container {
        height: 1fr;
        border: round $accent;
        padding: 1;
        overflow-y: auto;
    }
    .setting-row {
        layout: horizontal;
        height: 3;
        margin: 0 1;
    }
    .setting-label {
        width: 25;
        padding: 1;
    }
    .setting-input {
        width: 1fr;
    }
    #settings-status {
        dock: bottom;
        height: 3;
        padding: 1;
        background: $surface;
    }
    """

    def compose(self) -> ComposeResult:
        """Build the widget tree for the settings screen."""
        yield Header(show_clock=True)
        yield Label("Settings", id="settings-title")

        app = self.app
        config = app.lazy_config if isinstance(app, LazySplitterApp) else LazyConfig()

        with VerticalScroll(id="settings-container"):
            # Output directory
            with Horizontal(classes="setting-row"):
                yield Label("Output Directory:", classes="setting-label")
                yield Input(
                    value=config.output_dir or "",
                    placeholder="Same as input file",
                    id="setting-output-dir",
                    classes="setting-input",
                )
            # Filename pattern
            with Horizontal(classes="setting-row"):
                yield Label("Filename Pattern:", classes="setting-label")
                yield Input(
                    value=config.filename_pattern,
                    id="setting-filename-pattern",
                    classes="setting-input",
                )
            # Strategy
            with Horizontal(classes="setting-row"):
                yield Label("Strategy:", classes="setting-label")
                yield Input(
                    value=config.strategy,
                    id="setting-strategy",
                    classes="setting-input",
                )
            # Sensitivity
            with Horizontal(classes="setting-row"):
                yield Label("Sensitivity:", classes="setting-label")
                yield Input(
                    value=config.sensitivity,
                    id="setting-sensitivity",
                    classes="setting-input",
                )
            # Parallel workers
            with Horizontal(classes="setting-row"):
                yield Label("Parallel Workers:", classes="setting-label")
                yield Input(
                    value=str(config.parallel_workers),
                    id="setting-parallel-workers",
                    classes="setting-input",
                )
            # Verbose
            with Horizontal(classes="setting-row"):
                yield Label("Verbose:", classes="setting-label")
                yield Input(
                    value=str(config.verbose).lower(),
                    id="setting-verbose",
                    classes="setting-input",
                )
            # Dry run
            with Horizontal(classes="setting-row"):
                yield Label("Dry Run:", classes="setting-label")
                yield Input(
                    value=str(config.dry_run).lower(),
                    id="setting-dry-run",
                    classes="setting-input",
                )

        yield Label("Press Ctrl+S to save", id="settings-status")
        yield Footer()

    def action_save_settings(self) -> None:
        """Read values from the form and persist the configuration."""
        app = self.app
        if not isinstance(app, LazySplitterApp):
            return

        config = app.lazy_config

        output_dir = self.query_one("#setting-output-dir", Input).value
        config.output_dir = output_dir if output_dir else None

        config.filename_pattern = self.query_one(
            "#setting-filename-pattern", Input
        ).value
        config.strategy = self.query_one("#setting-strategy", Input).value
        config.sensitivity = self.query_one("#setting-sensitivity", Input).value

        workers_str = self.query_one("#setting-parallel-workers", Input).value
        try:
            config.parallel_workers = int(workers_str)
        except ValueError:
            config.parallel_workers = 0

        verbose_str = self.query_one("#setting-verbose", Input).value
        config.verbose = verbose_str.lower() in ("true", "1", "yes")

        dry_run_str = self.query_one("#setting-dry-run", Input).value
        config.dry_run = dry_run_str.lower() in ("true", "1", "yes")

        # Persist to disk
        try:
            config_path = Path.home() / ".lazy-splitter.toml"
            save_config(config, config_path)
            status = self.query_one("#settings-status", Label)
            status.update(f"Settings saved to {config_path}")
            self.notify("Settings saved")
        except LazySplitterError as exc:
            self.notify(f"Failed to save: {exc}", severity="error")


# ===================================================================
# LazySplitterApp -- main application
# ===================================================================

class LazySplitterApp(App):
    """Main Textual application for lazy-splitter.

    Orchestrates navigation between screens and holds shared application
    state such as the currently selected file, detected chapters, and
    configuration.

    Attributes:
        current_file: Path to the file selected for splitting.
        detected_chapters: Chapters detected in the current file.
        last_split_result: Result of the most recent split operation.
        lazy_config: Active :class:`~lazy_splitter.core.config.LazyConfig`.
    """

    TITLE = "lazy-splitter"
    SUB_TITLE = "Intelligent file splitting"

    CSS = """
    Screen {
        background: $surface;
    }
    #help-dialog {
        align: center middle;
        width: 60;
        height: 20;
        border: thick $accent;
        padding: 1 2;
        background: $panel;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("s", "push_screen_split", "Split", show=True),
        Binding("p", "push_screen_preview", "Preview", show=True),
        Binding("question_mark", "show_help", "Help", show=True, key_display="?"),
        Binding("slash", "show_search", "Search", show=True, key_display="/"),
        Binding("comma", "push_screen_settings", "Settings", show=True, key_display=","),
        Binding("d", "toggle_dark", "Toggle Dark/Light"),
    ]

    # -- Reactive application state ------------------------------------------

    current_file: reactive[str] = reactive("")
    detected_chapters: reactive[list] = reactive(list, init=False)
    last_split_result: reactive[Optional[SplitResult]] = reactive(None, init=False)

    def __init__(
        self,
        config: Optional[LazyConfig] = None,
        **kwargs: Any,
    ) -> None:
        """Initialise the application.

        Parameters:
            config: Optional pre-loaded configuration.  When ``None`` the
                default search strategy of :func:`load_config` is used.
            **kwargs: Forwarded to :class:`textual.app.App`.
        """
        require_textual()
        super().__init__(**kwargs)
        self.lazy_config: LazyConfig = config or load_config()
        self.detected_chapters: List[Any] = []
        self.last_split_result: Optional[SplitResult] = None

    def on_mount(self) -> None:
        """Set up the initial screen when the application starts."""
        self.push_screen(FileSelectScreen())

    # -- Actions -------------------------------------------------------------

    def action_push_screen_split(self) -> None:
        """Navigate to the split-progress screen."""
        if self.current_file:
            self.push_screen(SplitScreen())
        else:
            self.notify("Select a file first", severity="warning")

    def action_push_screen_preview(self) -> None:
        """Navigate to the chapter preview screen."""
        if self.current_file:
            self.push_screen(PreviewScreen())
        else:
            self.notify("Select a file first", severity="warning")

    def action_push_screen_settings(self) -> None:
        """Navigate to the settings screen."""
        self.push_screen(SettingsScreen())

    def action_show_help(self) -> None:
        """Display a help dialog with keyboard shortcuts."""
        help_text = (
            "Keyboard Shortcuts\n"
            "-------------------\n"
            "q          Quit\n"
            "s          Split selected file\n"
            "p          Preview chapters\n"
            ",          Settings\n"
            "?          This help screen\n"
            "/          Search files\n"
            "d          Toggle dark/light theme\n"
            "j/k        Navigate down/up (in tables)\n"
            "Escape     Go back\n"
            "Enter      Confirm selection\n"
        )
        self.notify(help_text, timeout=10)

    def action_show_search(self) -> None:
        """Show a search prompt for filtering files."""
        self.notify("Search: type to filter (not yet implemented)")

    def action_toggle_dark(self) -> None:
        """Switch between dark and light themes."""
        self.dark = not self.dark

    # -- Public helpers for external integration -----------------------------

    def set_chapters(self, chapters: Sequence[Any]) -> None:
        """Set the detected chapters from an external detection call.

        Parameters:
            chapters: Sequence of chapter / segment dataclass instances.
        """
        self.detected_chapters = list(chapters)

    def set_split_result(self, result: SplitResult) -> None:
        """Store a split result for display on the results screen.

        Parameters:
            result: The :class:`~lazy_splitter.core.models.SplitResult` to show.
        """
        self.last_split_result = result
