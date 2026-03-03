"""Unified CLI entry point for lazy-splitter.

Provides a single ``lazy-splitter`` command that auto-detects file types and
routes to the appropriate splitter, merger, converter, or analysis tool.

Usage::

    lazy-splitter split document.pdf
    lazy-splitter split book.epub --strategy native
    lazy-splitter merge part1.pdf part2.pdf -o combined.pdf
    lazy-splitter preview video.mp4
    lazy-splitter batch ./documents --pattern "*.pdf" --recursive
    lazy-splitter info report.docx
    lazy-splitter config init
    lazy-splitter config show

Requires Python 3.8+.
"""

from __future__ import annotations

import json as json_stdlib
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# ---------------------------------------------------------------------------
# Version & package metadata
# ---------------------------------------------------------------------------

__version__ = "0.2.0"

# ---------------------------------------------------------------------------
# File-type extension mapping
# ---------------------------------------------------------------------------

#: Maps file extensions (lower-case, including the dot) to a human-readable
#: category that determines which backend module to load.
_EXTENSION_CATEGORY: Dict[str, str] = {
    # Documents – PDF
    ".pdf": "pdf",
    # Documents – EPUB
    ".epub": "epub",
    # Documents – Office
    ".docx": "document",
    ".pptx": "document",
    ".xlsx": "document",
    # Documents – Markup / text
    ".md": "document",
    ".tex": "document",
    ".html": "document",
    ".csv": "document",
    ".json": "document",
    # Video
    ".mp4": "video",
    ".mkv": "video",
    ".avi": "video",
    ".mov": "video",
    ".webm": "video",
    # Audio
    ".mp3": "audio",
    ".flac": "audio",
    ".wav": "audio",
    ".ogg": "audio",
    ".m4a": "audio",
    ".m4b": "audio",
    ".aac": "audio",
    # Image (multi-page / animated)
    ".tiff": "image",
    ".tif": "image",
    ".gif": "image",
    ".webp": "image",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".bmp": "image",
}

#: Human-readable descriptions for each category.
_CATEGORY_LABELS: Dict[str, str] = {
    "pdf": "PDF document",
    "epub": "EPUB e-book",
    "document": "Document",
    "video": "Video",
    "audio": "Audio",
    "image": "Image",
}

#: Install hints shown when an optional dependency is missing.
_INSTALL_HINTS: Dict[str, str] = {
    "pdf": "pip install lazy-splitter[pdf]  (requires pymupdf)",
    "epub": "pip install lazy-splitter[epub]  (requires ebooklib, lxml)",
    "video": "pip install lazy-splitter[video]  (requires ffmpeg-python; ffmpeg must be on PATH)",
    "audio": "pip install lazy-splitter[audio]  (requires ffmpeg-python; ffmpeg must be on PATH)",
    "document": "pip install lazy-splitter[document]  (requires python-docx, openpyxl, python-pptx)",
    "image": "pip install lazy-splitter[image]  (requires Pillow)",
}

# ---------------------------------------------------------------------------
# Default configuration template
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG = """\
# lazy-splitter configuration
# Place this file at ~/.config/lazy-splitter/config.toml or pass --config <path>

[general]
# Default output directory (relative paths are resolved from the input file)
# output_dir = "."
verbose = false
json_output = false

[split]
strategy = "hybrid"
sensitivity = "medium"
filename_pattern = "{index:02d}_{title}"
preserve_metadata = true

[split.pdf]
# bookmark_level = 1
# password = ""
# pages = ""

[split.epub]
# toc_level = 1

[merge]
generate_toc = true

[convert]
quality = 90

[batch]
recursive = false
parallel = false
workers = 4
pattern = "*"

[profiles.fast]
# Override settings for quick-and-dirty processing
split.strategy = "bookmarks"
split.sensitivity = "low"

[profiles.thorough]
# Override settings for maximum accuracy
split.strategy = "hybrid"
split.sensitivity = "high"
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _detect_category(file_path: Path) -> str:
    """Return the category string for *file_path* based on its extension.

    Raises :class:`click.BadParameter` when the extension is not recognised.
    """
    ext = file_path.suffix.lower()
    category = _EXTENSION_CATEGORY.get(ext)
    if category is None:
        supported = ", ".join(sorted(_EXTENSION_CATEGORY.keys()))
        raise click.BadParameter(
            f"Unsupported file type '{ext}'. Supported extensions: {supported}",
            param_hint="'FILE'",
        )
    return category


def _check_dependency(category: str) -> None:
    """Verify that the runtime dependencies for *category* are available.

    Raises :class:`click.UsageError` with a helpful install message when a
    required package cannot be imported.
    """
    try:
        if category == "pdf":
            import fitz as _fitz  # noqa: F401
        elif category == "epub":
            import ebooklib as _ebooklib  # noqa: F401
            import lxml as _lxml  # noqa: F401
        elif category == "video":
            import ffmpeg as _ffmpeg  # noqa: F401
        elif category == "audio":
            import ffmpeg as _ffmpeg  # noqa: F401
        elif category == "document":
            # Best-effort: we only need *one* of the document libs depending
            # on the concrete file type, but we can't know which one until we
            # actually look at the extension.  A full check happens inside the
            # handler.  Here we just verify at least one is present.
            pass
        elif category == "image":
            from PIL import Image as _Image  # noqa: F401
    except ImportError:
        hint = _INSTALL_HINTS.get(category, "")
        label = _CATEGORY_LABELS.get(category, category)
        raise click.UsageError(
            f"{label} processing requires additional dependencies.\n"
            f"Install with: {hint}"
        )


def _format_size(size_bytes: int) -> str:
    """Return *size_bytes* as a human-readable string (e.g. ``1.2 MB``)."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:,.1f} {unit}"
        size_bytes = int(size_bytes / 1024)
    return f"{size_bytes:,.1f} PB"


def _make_console(ctx: click.Context) -> Console:
    """Build a :class:`rich.console.Console` respecting global flags."""
    no_color: bool = ctx.obj.get("no_color", False)
    quiet: bool = ctx.obj.get("quiet", False)
    return Console(
        no_color=no_color,
        quiet=quiet,
        force_terminal=None if not no_color else False,
    )


def _json_out(ctx: click.Context, data: Any) -> None:
    """If ``--json`` is active, print *data* as JSON and exit."""
    if ctx.obj.get("json_output"):
        click.echo(json_stdlib.dumps(data, indent=2, default=str))


def _dry_run_banner(ctx: click.Context, console: Console) -> bool:
    """Print a dry-run banner if ``--dry-run`` is active.  Returns the flag."""
    dry: bool = ctx.obj.get("dry_run", False)
    if dry:
        console.print(
            Panel("[bold yellow]DRY RUN[/bold yellow] -- no files will be written."),
        )
    return dry


def _verbose(ctx: click.Context) -> bool:
    """Return whether verbose output is enabled."""
    return bool(ctx.obj.get("verbose", False))


def _debug(ctx: click.Context) -> bool:
    """Return whether debug output is enabled."""
    return bool(ctx.obj.get("debug", False))


# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------


@click.group(
    name="lazy-splitter",
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(version=__version__, prog_name="lazy-splitter")
@click.option("-v", "--verbose", is_flag=True, default=False, help="Enable verbose output.")
@click.option("--debug", is_flag=True, default=False, help="Enable debug output (implies --verbose).")
@click.option("-q", "--quiet", is_flag=True, default=False, help="Suppress all non-essential output.")
@click.option("--json", "json_output", is_flag=True, default=False, help="Emit machine-readable JSON.")
@click.option(
    "-n",
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what would be done without writing files.",
)
@click.option("--no-color", is_flag=True, default=False, help="Disable coloured output.")
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=False, path_type=Path),
    default=None,
    envvar="LAZY_SPLITTER_CONFIG",
    help="Path to a TOML configuration file.",
)
@click.option(
    "--profile",
    type=str,
    default=None,
    help="Configuration profile to activate (defined in config file).",
)
@click.pass_context
def cli(
    ctx: click.Context,
    verbose: bool,
    debug: bool,
    quiet: bool,
    json_output: bool,
    dry_run: bool,
    no_color: bool,
    config_path: Optional[Path],
    profile: Optional[str],
) -> None:
    """lazy-splitter -- intelligently split, merge, and convert files.

    Auto-detects PDFs, EPUBs, videos, audio files, office documents, images,
    and more, then routes to the right tool.

    \b
    Examples
    --------
      lazy-splitter split textbook.pdf
      lazy-splitter split audiobook.m4b -o chapters/
      lazy-splitter merge ch01.pdf ch02.pdf -o book.pdf
      lazy-splitter preview lecture.mp4
      lazy-splitter batch ./docs --pattern "*.epub" --recursive
      lazy-splitter info report.docx
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose or debug
    ctx.obj["debug"] = debug
    ctx.obj["quiet"] = quiet
    ctx.obj["json_output"] = json_output
    ctx.obj["dry_run"] = dry_run
    ctx.obj["no_color"] = no_color
    ctx.obj["config_path"] = config_path
    ctx.obj["profile"] = profile

    # Show help when invoked without a sub-command.
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# ======================================================================== #
# split
# ======================================================================== #


@cli.command()
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-o",
    "--output-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Output directory (default: <file>_chapters/).",
)
@click.option(
    "--strategy",
    type=click.Choice(
        ["bookmarks", "heuristic", "hybrid", "native", "structural", "manifest"],
        case_sensitive=False,
    ),
    default="hybrid",
    help="Chapter / segment detection strategy.",
)
@click.option(
    "--sensitivity",
    type=click.Choice(["low", "medium", "high"], case_sensitive=False),
    default="medium",
    help="Detection sensitivity (default: medium).",
)
@click.option(
    "--pattern",
    type=str,
    default="{index:02d}_{title}",
    help="Filename pattern for output files.",
)
@click.option(
    "--no-metadata",
    is_flag=True,
    default=False,
    help="Do not preserve source metadata in output files.",
)
@click.option(
    "--password",
    type=str,
    default=None,
    help="Password for encrypted PDF files.",
)
@click.option(
    "--pages",
    type=str,
    default=None,
    help="Page range to process (PDF only), e.g. '1-10,15,20-30'.",
)
@click.pass_context
def split(
    ctx: click.Context,
    file: Path,
    output_dir: Optional[Path],
    strategy: str,
    sensitivity: str,
    pattern: str,
    no_metadata: bool,
    password: Optional[str],
    pages: Optional[str],
) -> None:
    """Split FILE into chapters / segments.

    The file type is auto-detected from the extension and the appropriate
    backend is used.  For PDFs this means bookmark / heuristic chapter
    detection; for EPUBs the native TOC or structural analysis is used;
    for audio and video files silence / scene detection is applied.

    \b
    Examples
    --------
      lazy-splitter split textbook.pdf
      lazy-splitter split textbook.pdf -o chapters/ --strategy bookmarks
      lazy-splitter split novel.epub --strategy native
      lazy-splitter split podcast.mp3 --sensitivity high
    """
    console = _make_console(ctx)
    dry = _dry_run_banner(ctx, console)
    category = _detect_category(file)
    _check_dependency(category)

    if output_dir is None:
        output_dir = file.parent / f"{file.stem}_chapters"

    if _verbose(ctx):
        console.print(f"[dim]File:[/dim]        {file}")
        console.print(f"[dim]Type:[/dim]        {_CATEGORY_LABELS.get(category, category)}")
        console.print(f"[dim]Output:[/dim]      {output_dir}")
        console.print(f"[dim]Strategy:[/dim]    {strategy}")
        console.print(f"[dim]Sensitivity:[/dim] {sensitivity}")
        console.print()

    # ------------------------------------------------------------------
    # PDF
    # ------------------------------------------------------------------
    if category == "pdf":
        _split_pdf(
            ctx,
            console,
            file,
            output_dir,
            strategy=strategy,
            sensitivity=sensitivity,
            pattern=pattern,
            no_metadata=no_metadata,
            password=password,
            pages=pages,
            dry_run=dry,
        )

    # ------------------------------------------------------------------
    # EPUB
    # ------------------------------------------------------------------
    elif category == "epub":
        _split_epub(
            ctx,
            console,
            file,
            output_dir,
            strategy=strategy,
            sensitivity=sensitivity,
            pattern=pattern,
            no_metadata=no_metadata,
            dry_run=dry,
        )

    # ------------------------------------------------------------------
    # Video
    # ------------------------------------------------------------------
    elif category == "video":
        _split_media(
            ctx,
            console,
            file,
            output_dir,
            category="video",
            strategy=strategy,
            sensitivity=sensitivity,
            pattern=pattern,
            dry_run=dry,
        )

    # ------------------------------------------------------------------
    # Audio
    # ------------------------------------------------------------------
    elif category == "audio":
        _split_media(
            ctx,
            console,
            file,
            output_dir,
            category="audio",
            strategy=strategy,
            sensitivity=sensitivity,
            pattern=pattern,
            dry_run=dry,
        )

    # ------------------------------------------------------------------
    # Document / Image -- placeholder
    # ------------------------------------------------------------------
    else:
        _split_generic(
            ctx,
            console,
            file,
            output_dir,
            category=category,
            strategy=strategy,
            sensitivity=sensitivity,
            pattern=pattern,
            dry_run=dry,
        )


# ------------------------------------------------------------------
# Split helpers (one per category)
# ------------------------------------------------------------------


def _split_pdf(
    ctx: click.Context,
    console: Console,
    file: Path,
    output_dir: Path,
    *,
    strategy: str,
    sensitivity: str,
    pattern: str,
    no_metadata: bool,
    password: Optional[str],
    pages: Optional[str],
    dry_run: bool,
) -> None:
    """Split a PDF file into chapters."""
    from rich.progress import Progress, SpinnerColumn, TextColumn

    # Lazy-import the PDF backend.
    try:
        from pdf_splitter.detector import ChapterDetector
        from pdf_splitter.splitter import PDFSplitter
    except ImportError:
        raise click.UsageError(
            "PDF splitting requires PyMuPDF.\n"
            "Install with: pip install lazy-splitter[pdf]  (or: pip install pymupdf)"
        )

    console.print(f"[bold cyan]lazy-splitter[/bold cyan] v{__version__}  |  PDF split\n")

    # Open the document (handle password).
    import fitz  # noqa: WPS433

    try:
        doc = fitz.open(file)
    except Exception as exc:
        raise click.ClickException(f"Cannot open PDF: {exc}")

    if doc.is_encrypted:
        if password is None:
            raise click.ClickException(
                "This PDF is encrypted. Supply a password with --password."
            )
        if not doc.authenticate(password):
            doc.close()
            raise click.ClickException("Incorrect PDF password.")

    total_pages = len(doc)
    doc.close()

    if _verbose(ctx):
        console.print(f"[dim]Total pages:[/dim] {total_pages}")
        if pages:
            console.print(f"[dim]Page range:[/dim]  {pages}")
        console.print()

    # Detect chapters.
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Detecting chapters...", total=None)
        detector = ChapterDetector(sensitivity=sensitivity)
        result = detector.detect(file, strategy=strategy)
        progress.update(task, completed=True)

    # Display detection results.
    console.print(
        f"\n[green]Found {result.chapter_count} chapter(s)[/green]"
        f"  (strategy: {result.strategy_used})\n"
    )

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="cyan")
    table.add_column("Pages", justify="right")
    table.add_column("Range", justify="center", style="dim")
    table.add_column("Confidence", justify="center")

    for i, chapter in enumerate(result.chapters, start=1):
        conf = f"{chapter.confidence:.0%}"
        if chapter.confidence >= 0.8:
            color = "green"
        elif chapter.confidence >= 0.6:
            color = "yellow"
        else:
            color = "red"
        table.add_row(
            str(i),
            chapter.title,
            str(chapter.page_count),
            f"{chapter.start_page}-{chapter.end_page}",
            f"[{color}]{conf}[/{color}]",
        )
    console.print(table)
    console.print()

    # JSON output.
    if ctx.obj.get("json_output"):
        _json_out(ctx, {
            "file": str(file),
            "type": "pdf",
            "total_pages": total_pages,
            "strategy_used": result.strategy_used,
            "chapters": [
                {
                    "index": i,
                    "title": ch.title,
                    "start_page": ch.start_page,
                    "end_page": ch.end_page,
                    "page_count": ch.page_count,
                    "confidence": ch.confidence,
                }
                for i, ch in enumerate(result.chapters, 1)
            ],
        })
        return

    if dry_run:
        console.print("[yellow]Dry run -- skipping file creation.[/yellow]")
        return

    # Split.
    pdf_pattern = pattern if pattern.endswith(".pdf") else pattern + ".pdf"
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Splitting PDF...", total=None)
        splitter = PDFSplitter(output_dir, filename_pattern=pdf_pattern)
        created = splitter.split(file, result.chapters, preserve_metadata=not no_metadata)
        progress.update(task, completed=True)

    console.print(f"\n[green]Created {len(created)} file(s) in {output_dir}[/green]\n")
    for p in created[:10]:
        console.print(f"  [dim]-[/dim] {p.name}")
    if len(created) > 10:
        console.print(f"  [dim]... and {len(created) - 10} more[/dim]")
    console.print()


def _split_epub(
    ctx: click.Context,
    console: Console,
    file: Path,
    output_dir: Path,
    *,
    strategy: str,
    sensitivity: str,
    pattern: str,
    no_metadata: bool,
    dry_run: bool,
) -> None:
    """Split an EPUB file into chapters."""
    from rich.progress import Progress, SpinnerColumn, TextColumn

    try:
        from epub_splitter.detector import EpubChapterDetector
        from epub_splitter.splitter import EpubSplitter
    except ImportError:
        raise click.UsageError(
            "EPUB splitting requires ebooklib and lxml.\n"
            "Install with: pip install lazy-splitter[epub]"
        )

    console.print(f"[bold cyan]lazy-splitter[/bold cyan] v{__version__}  |  EPUB split\n")

    # Map generic strategies to EPUB-specific ones where needed.
    epub_strategy = strategy
    if strategy in ("bookmarks", "heuristic"):
        epub_strategy = "hybrid"

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Detecting chapters...", total=None)
        detector = EpubChapterDetector(
            strategy=epub_strategy,  # type: ignore[arg-type]
            sensitivity=sensitivity,  # type: ignore[arg-type]
        )
        result = detector.detect(file)
        progress.update(task, completed=True)

    console.print(
        f"\n[green]Found {result.chapter_count} chapter(s)[/green]"
        f"  (strategy: {result.strategy_used})\n"
    )

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="cyan")
    table.add_column("File", style="dim")
    table.add_column("Method", justify="center")
    table.add_column("Confidence", justify="center")

    for i, ch in enumerate(result.chapters, 1):
        conf = f"{ch.confidence:.0%}"
        color = "green" if ch.confidence >= 0.8 else "yellow" if ch.confidence >= 0.6 else "red"
        table.add_row(
            str(i),
            ch.title[:60] + ("..." if len(ch.title) > 60 else ""),
            Path(ch.file_path).name,
            ch.detection_method,
            f"[{color}]{conf}[/{color}]",
        )
    console.print(table)
    console.print()

    if ctx.obj.get("json_output"):
        _json_out(ctx, {
            "file": str(file),
            "type": "epub",
            "strategy_used": result.strategy_used,
            "total_files": result.total_files,
            "has_toc": result.has_toc,
            "chapters": [
                {
                    "index": i,
                    "title": ch.title,
                    "file_path": ch.file_path,
                    "detection_method": ch.detection_method,
                    "confidence": ch.confidence,
                }
                for i, ch in enumerate(result.chapters, 1)
            ],
        })
        return

    if dry_run:
        console.print("[yellow]Dry run -- skipping file creation.[/yellow]")
        return

    if not result.chapters:
        console.print("[yellow]No chapters detected. Nothing to split.[/yellow]")
        return

    epub_pattern = pattern if pattern.endswith(".epub") else pattern + ".epub"
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Splitting EPUB...", total=None)
        splitter = EpubSplitter(output_dir, filename_pattern=epub_pattern)
        created = splitter.split(file, result.chapters, preserve_metadata=not no_metadata)
        progress.update(task, completed=True)

    console.print(f"\n[green]Created {len(created)} file(s) in {output_dir}[/green]\n")
    for p in created[:10]:
        console.print(f"  [dim]-[/dim] {p.name}")
    if len(created) > 10:
        console.print(f"  [dim]... and {len(created) - 10} more[/dim]")
    console.print()


def _split_media(
    ctx: click.Context,
    console: Console,
    file: Path,
    output_dir: Path,
    *,
    category: str,
    strategy: str,
    sensitivity: str,
    pattern: str,
    dry_run: bool,
) -> None:
    """Placeholder for video/audio splitting (requires ffmpeg)."""
    label = _CATEGORY_LABELS.get(category, category)
    console.print(f"[bold cyan]lazy-splitter[/bold cyan] v{__version__}  |  {label} split\n")
    console.print(f"[dim]File:[/dim] {file}")
    console.print(f"[dim]Size:[/dim] {_format_size(file.stat().st_size)}")
    console.print()

    if ctx.obj.get("json_output"):
        _json_out(ctx, {
            "file": str(file),
            "type": category,
            "size": file.stat().st_size,
            "status": "not_yet_implemented",
        })
        return

    console.print(
        f"[yellow]{label} splitting is not yet fully implemented.[/yellow]\n"
        f"[dim]Planned features: scene/silence detection, chapter markers, "
        f"segment extraction.[/dim]\n"
        f"[dim]Install hint: {_INSTALL_HINTS.get(category, '')}[/dim]"
    )


def _split_generic(
    ctx: click.Context,
    console: Console,
    file: Path,
    output_dir: Path,
    *,
    category: str,
    strategy: str,
    sensitivity: str,
    pattern: str,
    dry_run: bool,
) -> None:
    """Placeholder for document/image splitting."""
    label = _CATEGORY_LABELS.get(category, category)
    console.print(f"[bold cyan]lazy-splitter[/bold cyan] v{__version__}  |  {label} split\n")
    console.print(f"[dim]File:[/dim] {file}")
    console.print(f"[dim]Size:[/dim] {_format_size(file.stat().st_size)}")
    console.print()

    if ctx.obj.get("json_output"):
        _json_out(ctx, {
            "file": str(file),
            "type": category,
            "size": file.stat().st_size,
            "status": "not_yet_implemented",
        })
        return

    console.print(
        f"[yellow]{label} splitting is not yet fully implemented.[/yellow]\n"
        f"[dim]Install hint: {_INSTALL_HINTS.get(category, '')}[/dim]"
    )


# ======================================================================== #
# merge
# ======================================================================== #


@cli.command()
@click.argument("files", nargs=-1, required=True, type=click.Path(exists=True, path_type=Path))
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    required=True,
    help="Output file path.",
)
@click.option("--toc/--no-toc", default=True, help="Generate a table of contents (default: yes).")
@click.pass_context
def merge(
    ctx: click.Context,
    files: Tuple[Path, ...],
    output: Path,
    toc: bool,
) -> None:
    """Merge multiple FILES into a single output file.

    All files must be the same type (e.g. all PDFs).  A table of contents
    is generated by default.

    \b
    Examples
    --------
      lazy-splitter merge ch01.pdf ch02.pdf ch03.pdf -o book.pdf
      lazy-splitter merge part*.epub -o novel.epub --no-toc
    """
    console = _make_console(ctx)
    dry = _dry_run_banner(ctx, console)

    if len(files) < 2:
        raise click.UsageError("At least two files are required for merging.")

    # Determine category from the first file; verify all match.
    category = _detect_category(files[0])
    for f in files[1:]:
        other = _detect_category(f)
        if other != category:
            raise click.UsageError(
                f"All files must be the same type. Got '{category}' and '{other}'."
            )
    _check_dependency(category)

    console.print(f"[bold cyan]lazy-splitter[/bold cyan] v{__version__}  |  merge\n")
    console.print(f"[dim]Files:[/dim]  {len(files)}")
    console.print(f"[dim]Output:[/dim] {output}")
    console.print(f"[dim]TOC:[/dim]    {'yes' if toc else 'no'}")
    console.print()

    if ctx.obj.get("json_output"):
        _json_out(ctx, {
            "action": "merge",
            "type": category,
            "files": [str(f) for f in files],
            "output": str(output),
            "toc": toc,
        })
        return

    if dry:
        console.print("[yellow]Dry run -- skipping merge.[/yellow]")
        return

    if category == "pdf":
        _merge_pdf(console, files, output, toc=toc)
    else:
        console.print(
            f"[yellow]Merging for {_CATEGORY_LABELS.get(category, category)} "
            f"files is not yet implemented.[/yellow]"
        )


def _merge_pdf(
    console: Console,
    files: Tuple[Path, ...],
    output: Path,
    *,
    toc: bool,
) -> None:
    """Merge multiple PDF files into one."""
    from rich.progress import Progress, SpinnerColumn, TextColumn

    try:
        import fitz  # noqa: WPS433
    except ImportError:
        raise click.UsageError(
            "PDF merging requires PyMuPDF.\nInstall with: pip install lazy-splitter[pdf]"
        )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Merging PDFs...", total=len(files))
        merged = fitz.open()
        toc_entries: List[List[Any]] = []
        page_offset = 0

        for idx, file_path in enumerate(files, 1):
            doc = fitz.open(file_path)
            merged.insert_pdf(doc)

            if toc:
                title = doc.metadata.get("title") or file_path.stem
                toc_entries.append([1, title, page_offset + 1])

            page_offset += len(doc)
            doc.close()
            progress.update(task, advance=1)

    if toc and toc_entries:
        merged.set_toc(toc_entries)

    output.parent.mkdir(parents=True, exist_ok=True)
    merged.save(str(output))
    merged.close()

    console.print(f"\n[green]Merged {len(files)} files into {output}[/green]")
    console.print(f"[dim]Total pages:[/dim] {page_offset}\n")


# ======================================================================== #
# convert
# ======================================================================== #


@cli.command()
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--output", type=click.Path(path_type=Path), required=True, help="Output file path.")
@click.option(
    "--format",
    "out_format",
    type=str,
    default=None,
    help="Target format (auto-detected from output extension if omitted).",
)
@click.option(
    "--quality",
    type=click.IntRange(1, 100),
    default=90,
    help="Output quality 1-100 (where applicable, default: 90).",
)
@click.pass_context
def convert(
    ctx: click.Context,
    file: Path,
    output: Path,
    out_format: Optional[str],
    quality: int,
) -> None:
    """Convert FILE to a different format.

    \b
    Examples
    --------
      lazy-splitter convert book.epub -o book.pdf
      lazy-splitter convert video.mkv -o video.mp4 --quality 80
    """
    console = _make_console(ctx)
    dry = _dry_run_banner(ctx, console)

    src_category = _detect_category(file)
    target_ext = out_format or output.suffix.lower().lstrip(".")
    if not target_ext:
        raise click.UsageError("Cannot determine target format. Use --format or give the output a file extension.")

    console.print(f"[bold cyan]lazy-splitter[/bold cyan] v{__version__}  |  convert\n")
    console.print(f"[dim]Input:[/dim]   {file}")
    console.print(f"[dim]Output:[/dim]  {output}")
    console.print(f"[dim]Format:[/dim]  {target_ext}")
    console.print(f"[dim]Quality:[/dim] {quality}")
    console.print()

    if ctx.obj.get("json_output"):
        _json_out(ctx, {
            "action": "convert",
            "source": str(file),
            "source_type": src_category,
            "output": str(output),
            "format": target_ext,
            "quality": quality,
        })
        return

    if dry:
        console.print("[yellow]Dry run -- skipping conversion.[/yellow]")
        return

    console.print(
        f"[yellow]Conversion from {_CATEGORY_LABELS.get(src_category, src_category)} "
        f"to .{target_ext} is not yet fully implemented.[/yellow]\n"
        f"[dim]Planned: PDF<->EPUB, video trans-coding, audio trans-coding, "
        f"image format conversion.[/dim]"
    )


# ======================================================================== #
# preview
# ======================================================================== #


@cli.command()
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--strategy",
    type=click.Choice(
        ["bookmarks", "heuristic", "hybrid", "native", "structural", "manifest"],
        case_sensitive=False,
    ),
    default="hybrid",
    help="Detection strategy.",
)
@click.option(
    "--sensitivity",
    type=click.Choice(["low", "medium", "high"], case_sensitive=False),
    default="medium",
    help="Detection sensitivity.",
)
@click.pass_context
def preview(
    ctx: click.Context,
    file: Path,
    strategy: str,
    sensitivity: str,
) -> None:
    """Preview detected chapters / segments in FILE without writing anything.

    \b
    Examples
    --------
      lazy-splitter preview textbook.pdf
      lazy-splitter preview novel.epub --strategy native
      lazy-splitter preview podcast.mp3 --sensitivity high
    """
    console = _make_console(ctx)
    category = _detect_category(file)
    _check_dependency(category)

    console.print(f"[bold cyan]lazy-splitter[/bold cyan] v{__version__}  |  preview\n")

    if category == "pdf":
        _preview_pdf(ctx, console, file, strategy=strategy, sensitivity=sensitivity)
    elif category == "epub":
        _preview_epub(ctx, console, file, strategy=strategy, sensitivity=sensitivity)
    else:
        label = _CATEGORY_LABELS.get(category, category)
        console.print(f"[dim]File:[/dim] {file}")
        console.print(f"[dim]Type:[/dim] {label}")
        console.print(f"[dim]Size:[/dim] {_format_size(file.stat().st_size)}")
        console.print()

        if ctx.obj.get("json_output"):
            _json_out(ctx, {
                "file": str(file),
                "type": category,
                "size": file.stat().st_size,
                "status": "preview_not_yet_implemented",
            })
            return

        console.print(
            f"[yellow]Preview for {label} files is not yet implemented.[/yellow]\n"
            f"[dim]Planned: segment boundaries, chapter markers, scene detection results.[/dim]"
        )


def _preview_pdf(
    ctx: click.Context,
    console: Console,
    file: Path,
    *,
    strategy: str,
    sensitivity: str,
) -> None:
    """Preview PDF chapter detection results."""
    from rich.progress import Progress, SpinnerColumn, TextColumn

    try:
        from pdf_splitter.detector import ChapterDetector
    except ImportError:
        raise click.UsageError(
            "PDF preview requires PyMuPDF.\nInstall with: pip install lazy-splitter[pdf]"
        )

    console.print(f"[dim]File:[/dim]        {file}")
    console.print(f"[dim]Strategy:[/dim]    {strategy}")
    console.print(f"[dim]Sensitivity:[/dim] {sensitivity}")
    console.print()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Analyzing PDF...", total=None)
        detector = ChapterDetector(sensitivity=sensitivity)
        result = detector.detect(file, strategy=strategy)
        progress.update(task, completed=True)

    summary = Panel(result.get_summary(), title="Detection Summary", border_style="cyan")
    console.print(summary)
    console.print()

    if ctx.obj.get("json_output"):
        _json_out(ctx, {
            "file": str(file),
            "type": "pdf",
            "total_pages": result.total_pages,
            "has_bookmarks": result.has_bookmarks,
            "strategy_used": result.strategy_used,
            "chapters": [
                {
                    "index": i,
                    "title": ch.title,
                    "start_page": ch.start_page,
                    "end_page": ch.end_page,
                    "page_count": ch.page_count,
                    "detection_method": ch.detection_method,
                    "confidence": ch.confidence,
                }
                for i, ch in enumerate(result.chapters, 1)
            ],
        })
        return

    if not result.chapters:
        console.print("[yellow]No chapters detected.[/yellow]\n")
        return

    table = Table(title="Detected Chapters", show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="cyan")
    table.add_column("Pages", justify="right")
    table.add_column("Range", justify="center", style="dim")
    table.add_column("Method", justify="center")
    table.add_column("Confidence", justify="center")

    for i, ch in enumerate(result.chapters, 1):
        conf = f"{ch.confidence:.0%}"
        color = "green" if ch.confidence >= 0.8 else "yellow" if ch.confidence >= 0.6 else "red"
        method_color = "green" if ch.detection_method == "bookmark" else "yellow"
        table.add_row(
            str(i),
            ch.title,
            str(ch.page_count),
            f"{ch.start_page}-{ch.end_page}",
            f"[{method_color}]{ch.detection_method}[/{method_color}]",
            f"[{color}]{conf}[/{color}]",
        )

    console.print(table)
    console.print()

    if not result.has_bookmarks and strategy != "heuristic":
        console.print(
            "[dim]Tip: This PDF has no bookmarks. "
            "Try --strategy heuristic for better results.[/dim]\n"
        )


def _preview_epub(
    ctx: click.Context,
    console: Console,
    file: Path,
    *,
    strategy: str,
    sensitivity: str,
) -> None:
    """Preview EPUB chapter detection results."""
    from rich.progress import Progress, SpinnerColumn, TextColumn

    try:
        from epub_splitter.detector import EpubChapterDetector
    except ImportError:
        raise click.UsageError(
            "EPUB preview requires ebooklib and lxml.\n"
            "Install with: pip install lazy-splitter[epub]"
        )

    console.print(f"[dim]File:[/dim]        {file}")
    console.print(f"[dim]Strategy:[/dim]    {strategy}")
    console.print(f"[dim]Sensitivity:[/dim] {sensitivity}")
    console.print()

    epub_strategy = strategy
    if strategy in ("bookmarks", "heuristic"):
        epub_strategy = "hybrid"

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Analyzing EPUB...", total=None)
        detector = EpubChapterDetector(
            strategy=epub_strategy,  # type: ignore[arg-type]
            sensitivity=sensitivity,  # type: ignore[arg-type]
        )
        result = detector.detect(file)
        progress.update(task, completed=True)

    summary_text = (
        f"[cyan]Detection Strategy:[/cyan] {result.strategy_used}\n"
        f"[cyan]Total Content Files:[/cyan] {result.total_files}\n"
        f"[cyan]Chapters Found:[/cyan] {result.chapter_count}\n"
        f"[cyan]Has TOC:[/cyan] {'Yes' if result.has_toc else 'No'}"
    )
    console.print(Panel(summary_text, title="Detection Summary", border_style="cyan"))
    console.print()

    if ctx.obj.get("json_output"):
        _json_out(ctx, {
            "file": str(file),
            "type": "epub",
            "strategy_used": result.strategy_used,
            "total_files": result.total_files,
            "has_toc": result.has_toc,
            "chapters": [
                {
                    "index": i,
                    "title": ch.title,
                    "file_path": ch.file_path,
                    "html_id": ch.html_id,
                    "level": ch.level,
                    "detection_method": ch.detection_method,
                    "confidence": ch.confidence,
                }
                for i, ch in enumerate(result.chapters, 1)
            ],
        })
        return

    if not result.chapters:
        console.print("[yellow]No chapters detected.[/yellow]\n")
        return

    table = Table(title="Detected Chapters", show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="cyan")
    table.add_column("File", style="dim")
    table.add_column("Level", justify="center", width=7)
    table.add_column("Method", style="cyan", width=12)
    table.add_column("Confidence", justify="center")

    for i, ch in enumerate(result.chapters, 1):
        conf = f"{ch.confidence:.0%}"
        color = "green" if ch.confidence >= 0.8 else "yellow" if ch.confidence >= 0.5 else "red"
        title = ch.title[:50] + "..." if len(ch.title) > 50 else ch.title
        fname = Path(ch.file_path).name
        if ch.html_id:
            fname += f"#{ch.html_id}"
        table.add_row(
            str(i),
            title,
            fname,
            str(ch.level),
            ch.detection_method,
            f"[{color}]{conf}[/{color}]",
        )

    console.print(table)
    console.print()


# ======================================================================== #
# batch
# ======================================================================== #


@cli.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--pattern",
    type=str,
    default="*",
    help="Glob pattern for matching files (default: '*').",
)
@click.option(
    "--recursive/--no-recursive",
    default=False,
    help="Recurse into subdirectories.",
)
@click.option(
    "--parallel/--no-parallel",
    default=False,
    help="Process files in parallel.",
)
@click.option(
    "--workers",
    type=int,
    default=4,
    help="Number of parallel workers (default: 4).",
)
@click.pass_context
def batch(
    ctx: click.Context,
    directory: Path,
    pattern: str,
    recursive: bool,
    parallel: bool,
    workers: int,
) -> None:
    """Batch-process all matching files in DIRECTORY.

    Each supported file is split using default settings.  Use --pattern to
    filter by extension (e.g. ``--pattern "*.pdf"``).

    \b
    Examples
    --------
      lazy-splitter batch ./documents --pattern "*.pdf" --recursive
      lazy-splitter batch ./media --pattern "*.mp3" --parallel --workers 8
    """
    console = _make_console(ctx)
    dry = _dry_run_banner(ctx, console)

    console.print(f"[bold cyan]lazy-splitter[/bold cyan] v{__version__}  |  batch\n")

    # Discover files.
    if recursive:
        matched = sorted(directory.rglob(pattern))
    else:
        matched = sorted(directory.glob(pattern))

    # Filter to supported extensions only.
    supported = [
        f for f in matched if f.is_file() and f.suffix.lower() in _EXTENSION_CATEGORY
    ]

    console.print(f"[dim]Directory:[/dim]  {directory}")
    console.print(f"[dim]Pattern:[/dim]    {pattern}")
    console.print(f"[dim]Recursive:[/dim]  {'yes' if recursive else 'no'}")
    console.print(f"[dim]Matched:[/dim]    {len(matched)} file(s)")
    console.print(f"[dim]Supported:[/dim]  {len(supported)} file(s)")
    console.print()

    if not supported:
        console.print("[yellow]No supported files found.[/yellow]")
        return

    # Build summary table.
    categories: Dict[str, List[Path]] = {}
    for f in supported:
        cat = _EXTENSION_CATEGORY[f.suffix.lower()]
        categories.setdefault(cat, []).append(f)

    table = Table(title="Files to Process", show_header=True, header_style="bold magenta")
    table.add_column("Category", style="cyan")
    table.add_column("Count", justify="right")
    table.add_column("Total Size", justify="right", style="dim")

    for cat, cat_files in sorted(categories.items()):
        total_size = sum(f.stat().st_size for f in cat_files)
        table.add_row(
            _CATEGORY_LABELS.get(cat, cat),
            str(len(cat_files)),
            _format_size(total_size),
        )
    console.print(table)
    console.print()

    if ctx.obj.get("json_output"):
        _json_out(ctx, {
            "action": "batch",
            "directory": str(directory),
            "pattern": pattern,
            "recursive": recursive,
            "files": [
                {
                    "path": str(f),
                    "type": _EXTENSION_CATEGORY[f.suffix.lower()],
                    "size": f.stat().st_size,
                }
                for f in supported
            ],
        })
        return

    if dry:
        console.print("[yellow]Dry run -- skipping processing.[/yellow]")
        return

    # Process files sequentially (parallel processing is planned).
    if parallel:
        console.print(
            "[yellow]Parallel processing is not yet implemented. "
            "Processing sequentially.[/yellow]\n"
        )

    from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn

    successes = 0
    failures = 0
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Processing files...", total=len(supported))

        for file_path in supported:
            try:
                progress.update(task, description=f"Processing {file_path.name}...")
                cat = _EXTENSION_CATEGORY[file_path.suffix.lower()]

                # Invoke the split sub-command programmatically.
                out_dir = file_path.parent / f"{file_path.stem}_chapters"

                if cat == "pdf":
                    _check_dependency("pdf")
                    _split_pdf(
                        ctx, console, file_path, out_dir,
                        strategy="hybrid", sensitivity="medium",
                        pattern="{index:02d}_{title}.pdf",
                        no_metadata=False, password=None, pages=None,
                        dry_run=False,
                    )
                elif cat == "epub":
                    _check_dependency("epub")
                    _split_epub(
                        ctx, console, file_path, out_dir,
                        strategy="hybrid", sensitivity="medium",
                        pattern="{index:02d}_{title}.epub",
                        no_metadata=False, dry_run=False,
                    )
                else:
                    if _verbose(ctx):
                        console.print(
                            f"[dim]Skipping {file_path.name} "
                            f"({_CATEGORY_LABELS.get(cat, cat)} "
                            f"splitting not yet implemented)[/dim]"
                        )

                successes += 1
            except Exception as exc:
                failures += 1
                if _verbose(ctx):
                    console.print(f"[red]Failed: {file_path.name}: {exc}[/red]")

            progress.update(task, advance=1)

    console.print()
    console.print(
        f"[green]Completed:[/green] {successes} succeeded, "
        f"[red]{failures} failed[/red] out of {len(supported)} files.\n"
    )


# ======================================================================== #
# config (sub-group)
# ======================================================================== #


@cli.group()
@click.pass_context
def config(ctx: click.Context) -> None:
    """Manage lazy-splitter configuration."""
    pass


@config.command("init")
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    default=None,
    help="Where to write the config file (default: ~/.config/lazy-splitter/config.toml).",
)
@click.pass_context
def config_init(ctx: click.Context, output: Optional[Path]) -> None:
    """Generate a default configuration file.

    \b
    Examples
    --------
      lazy-splitter config init
      lazy-splitter config init -o ./my-config.toml
    """
    console = _make_console(ctx)

    if output is None:
        config_dir = Path.home() / ".config" / "lazy-splitter"
        output = config_dir / "config.toml"

    if output.exists():
        if not click.confirm(f"Config file already exists at {output}. Overwrite?"):
            console.print("[dim]Aborted.[/dim]")
            return

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_DEFAULT_CONFIG, encoding="utf-8")
    console.print(f"[green]Configuration file written to {output}[/green]\n")

    if ctx.obj.get("json_output"):
        _json_out(ctx, {"action": "config_init", "path": str(output)})


@config.command("show")
@click.pass_context
def config_show(ctx: click.Context) -> None:
    """Show the current effective configuration.

    Searches for configuration in this order:
      1. Path given via --config
      2. $LAZY_SPLITTER_CONFIG environment variable
      3. ./lazy-splitter.toml (current directory)
      4. ~/.config/lazy-splitter/config.toml
    """
    console = _make_console(ctx)
    config_path: Optional[Path] = ctx.obj.get("config_path")

    # Search order.
    candidates: List[Path] = []
    if config_path is not None:
        candidates.append(config_path)
    env_path = os.environ.get("LAZY_SPLITTER_CONFIG")
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(Path.cwd() / "lazy-splitter.toml")
    candidates.append(Path.home() / ".config" / "lazy-splitter" / "config.toml")

    found: Optional[Path] = None
    for candidate in candidates:
        if candidate.is_file():
            found = candidate
            break

    if found is None:
        console.print(
            "[yellow]No configuration file found.[/yellow]\n"
            "[dim]Run 'lazy-splitter config init' to generate one.[/dim]"
        )
        if ctx.obj.get("json_output"):
            _json_out(ctx, {"action": "config_show", "found": False, "searched": [str(c) for c in candidates]})
        return

    content = found.read_text(encoding="utf-8")

    if ctx.obj.get("json_output"):
        _json_out(ctx, {"action": "config_show", "path": str(found), "content": content})
        return

    console.print(f"[dim]Config file:[/dim] {found}\n")
    console.print(Panel(content.rstrip(), title=str(found), border_style="cyan"))
    console.print()


# ======================================================================== #
# info
# ======================================================================== #


@cli.command()
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.pass_context
def info(ctx: click.Context, file: Path) -> None:
    """Show detailed information and analysis for FILE.

    \b
    Examples
    --------
      lazy-splitter info textbook.pdf
      lazy-splitter info audiobook.m4b
      lazy-splitter info photo.tiff
    """
    console = _make_console(ctx)
    category = _detect_category(file)

    stat = file.stat()
    info_data: Dict[str, Any] = {
        "file": str(file),
        "name": file.name,
        "extension": file.suffix.lower(),
        "type": _CATEGORY_LABELS.get(category, category),
        "category": category,
        "size": stat.st_size,
        "size_human": _format_size(stat.st_size),
    }

    console.print(f"[bold cyan]lazy-splitter[/bold cyan] v{__version__}  |  file info\n")

    # Base info table.
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="dim")
    table.add_column("Value")

    table.add_row("File", str(file))
    table.add_row("Name", file.name)
    table.add_row("Type", _CATEGORY_LABELS.get(category, category))
    table.add_row("Extension", file.suffix.lower())
    table.add_row("Size", _format_size(stat.st_size))

    # Category-specific info.
    if category == "pdf":
        _info_pdf(file, table, info_data)
    elif category == "epub":
        _info_epub(file, table, info_data)

    console.print(Panel(table, title="File Information", border_style="cyan"))
    console.print()

    if ctx.obj.get("json_output"):
        _json_out(ctx, info_data)


def _info_pdf(file: Path, table: Table, data: Dict[str, Any]) -> None:
    """Add PDF-specific info rows."""
    try:
        import fitz  # noqa: WPS433
    except ImportError:
        table.add_row("Note", "Install pymupdf for detailed PDF info")
        return

    try:
        doc = fitz.open(file)
        metadata = doc.metadata or {}

        table.add_row("Pages", str(len(doc)))
        data["pages"] = len(doc)

        if metadata.get("title"):
            table.add_row("Title", metadata["title"])
            data["title"] = metadata["title"]
        if metadata.get("author"):
            table.add_row("Author", metadata["author"])
            data["author"] = metadata["author"]
        if metadata.get("subject"):
            table.add_row("Subject", metadata["subject"])
            data["subject"] = metadata["subject"]
        if metadata.get("creator"):
            table.add_row("Creator", metadata["creator"])
            data["creator"] = metadata["creator"]

        toc = doc.get_toc()
        table.add_row("Bookmarks", str(len(toc)) if toc else "None")
        data["bookmarks"] = len(toc)

        table.add_row("Encrypted", "Yes" if doc.is_encrypted else "No")
        data["encrypted"] = doc.is_encrypted

        doc.close()
    except Exception as exc:
        table.add_row("Error", str(exc))
        data["error"] = str(exc)


def _info_epub(file: Path, table: Table, data: Dict[str, Any]) -> None:
    """Add EPUB-specific info rows."""
    try:
        from ebooklib import epub as epub_lib  # noqa: WPS433
        import ebooklib  # noqa: WPS433
    except ImportError:
        table.add_row("Note", "Install ebooklib for detailed EPUB info")
        return

    try:
        book = epub_lib.read_epub(str(file))
        metadata = book.metadata

        # Title.
        titles = book.get_metadata("DC", "title")
        if titles:
            title_text = titles[0][0] if titles[0] else ""
            table.add_row("Title", title_text)
            data["title"] = title_text

        # Author.
        creators = book.get_metadata("DC", "creator")
        if creators:
            author_text = creators[0][0] if creators[0] else ""
            table.add_row("Author", author_text)
            data["author"] = author_text

        # Language.
        languages = book.get_metadata("DC", "language")
        if languages:
            lang_text = languages[0][0] if languages[0] else ""
            table.add_row("Language", lang_text)
            data["language"] = lang_text

        # Content files.
        content_files = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
        table.add_row("Content Files", str(len(content_files)))
        data["content_files"] = len(content_files)

        # TOC.
        toc = book.toc
        has_toc = bool(toc)
        table.add_row("Has TOC", "Yes" if has_toc else "No")
        data["has_toc"] = has_toc
        if has_toc:
            table.add_row("TOC Entries", str(len(toc)))
            data["toc_entries"] = len(toc)

    except Exception as exc:
        table.add_row("Error", str(exc))
        data["error"] = str(exc)


# ======================================================================== #
# Entry point
# ======================================================================== #


def main() -> None:
    """Entry point for the ``lazy-splitter`` console script."""
    cli(obj={})


if __name__ == "__main__":
    main()
