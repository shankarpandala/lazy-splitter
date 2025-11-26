"""CLI interface for EPUB chapter splitter."""

from pathlib import Path
from typing import Optional
import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel

from epub_splitter.detector import EpubChapterDetector
from epub_splitter.splitter import EpubSplitter
from epub_splitter import __version__


console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="epub-splitter")
def main() -> None:
    """
    EPUB Chapter Splitter - Intelligently detect and split EPUB chapters.

    Detects chapters using native TOC, HTML structure analysis, or manifest,
    then splits the EPUB into separate files.
    """
    pass


@main.command()
@click.argument("epub_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-o",
    "--output-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Output directory for split EPUBs (default: <epub_name>_chapters/)",
)
@click.option(
    "--strategy",
    type=click.Choice(["native", "structural", "manifest", "hybrid"], case_sensitive=False),
    default="hybrid",
    help="Chapter detection strategy (default: hybrid)",
)
@click.option(
    "--sensitivity",
    type=click.Choice(["low", "medium", "high"], case_sensitive=False),
    default="medium",
    help="Detection sensitivity for structural analysis (default: medium)",
)
@click.option(
    "--toc-level",
    type=int,
    default=1,
    help="TOC hierarchy level to use for splitting (default: 1). Use 1 for parts, 2 for chapters, 3 for sections, etc.",
)
@click.option(
    "--pattern",
    type=str,
    default="{index:02d}_{title}.epub",
    help="Filename pattern for output files (default: {index:02d}_{title}.epub)",
)
@click.option("--no-metadata", is_flag=True, help="Do not preserve EPUB metadata in split files")
def split(
    epub_file: Path,
    output_dir: Optional[Path],
    strategy: str,
    sensitivity: str,
    toc_level: int,
    pattern: str,
    no_metadata: bool,
) -> None:
    """
    Split an EPUB file by detected chapters.

    EPUB_FILE: Path to the EPUB file to split

    Examples:

        epub-splitter split ebook.epub

        epub-splitter split ebook.epub -o chapters/

        epub-splitter split ebook.epub --strategy structural --sensitivity high
    """
    try:
        # Validate EPUB file
        if not epub_file.suffix.lower() == ".epub":
            console.print("[red]Error: Input file must be an EPUB[/red]")
            raise click.Abort()

        # Set default output directory
        if output_dir is None:
            output_dir = epub_file.parent / f"{epub_file.stem}_chapters"

        console.print(f"\n[bold cyan]EPUB Chapter Splitter[/bold cyan] v{__version__}\n")
        console.print(f"[dim]Input:[/dim] {epub_file}")
        console.print(f"[dim]Output:[/dim] {output_dir}")
        console.print(f"[dim]Strategy:[/dim] {strategy}")
        console.print(f"[dim]Sensitivity:[/dim] {sensitivity}")
        console.print(f"[dim]TOC Level:[/dim] {toc_level}\n")

        # Detect chapters
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Analyzing EPUB and detecting chapters...", total=None)
            detector = EpubChapterDetector(
                strategy=strategy, sensitivity=sensitivity, toc_level=toc_level
            )
            result = detector.detect(epub_file)

        # Display detection summary
        summary_panel = Panel(
            f"[cyan]Detection Strategy:[/cyan] {result.strategy_used}\n"
            f"[cyan]Total Content Files:[/cyan] {result.total_files}\n"
            f"[cyan]Chapters Found:[/cyan] {result.chapter_count}\n"
            f"[cyan]Has TOC:[/cyan] {'Yes' if result.has_toc else 'No'}",
            title="Detection Summary",
        )
        console.print(summary_panel)

        if not result.chapters:
            console.print("\n[yellow]No chapters detected. Nothing to split.[/yellow]")
            return

        # Check confidence levels
        low_confidence = [ch for ch in result.chapters if ch.confidence < 0.5]
        if low_confidence:
            console.print(
                f"\n[yellow]Warning: {len(low_confidence)} chapters have low confidence.[/yellow]"
            )
            if not click.confirm("Continue with splitting?"):
                console.print("[dim]Aborted.[/dim]")
                return

        # Split the EPUB
        console.print(f"\n[cyan]Splitting into {result.chapter_count} chapters...[/cyan]")

        splitter = EpubSplitter(output_dir, filename_pattern=pattern)

        with Progress(console=console) as progress:
            task = progress.add_task("[cyan]Creating chapter EPUBs...", total=len(result.chapters))

            created_files = splitter.split(
                epub_file, result.chapters, preserve_metadata=not no_metadata
            )

            progress.update(task, completed=len(result.chapters))

        # Display success message
        console.print(
            f"\n[bold green]✓ Successfully split into {len(created_files)} files[/bold green]"
        )
        console.print(f"[dim]Output directory:[/dim] {output_dir}\n")

    except click.Abort:
        raise
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {str(e)}")
        raise click.Abort()


@main.command()
@click.argument("epub_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--strategy",
    type=click.Choice(["native", "structural", "manifest", "hybrid"], case_sensitive=False),
    default="hybrid",
    help="Chapter detection strategy (default: hybrid)",
)
@click.option(
    "--sensitivity",
    type=click.Choice(["low", "medium", "high"], case_sensitive=False),
    default="medium",
    help="Detection sensitivity for structural analysis (default: medium)",
)
@click.option(
    "--toc-level",
    type=int,
    default=1,
    help="TOC hierarchy level to use (default: 1)",
)
def preview(
    epub_file: Path,
    strategy: str,
    sensitivity: str,
    toc_level: int,
) -> None:
    """
    Preview detected chapters without splitting.

    EPUB_FILE: Path to the EPUB file to analyze

    Examples:

        epub-splitter preview ebook.epub

        epub-splitter preview ebook.epub --strategy native

        epub-splitter preview ebook.epub --toc-level 2
    """
    try:
        # Validate EPUB file
        if not epub_file.suffix.lower() == ".epub":
            console.print("[red]Error: Input file must be an EPUB[/red]")
            raise click.Abort()

        console.print(f"\n[bold cyan]EPUB Chapter Splitter[/bold cyan] v{__version__}\n")
        console.print(f"[dim]File:[/dim] {epub_file}")
        console.print(f"[dim]Strategy:[/dim] {strategy}")
        console.print(f"[dim]Sensitivity:[/dim] {sensitivity}")
        console.print(f"[dim]TOC Level:[/dim] {toc_level}\n")

        # Detect chapters
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Analyzing EPUB and detecting chapters...", total=None)
            detector = EpubChapterDetector(
                strategy=strategy, sensitivity=sensitivity, toc_level=toc_level
            )
            result = detector.detect(epub_file)

        # Display detection summary
        summary_panel = Panel(
            f"[cyan]Detection Strategy:[/cyan] {result.strategy_used}\n"
            f"[cyan]Total Content Files:[/cyan] {result.total_files}\n"
            f"[cyan]Chapters Found:[/cyan] {result.chapter_count}\n"
            f"[cyan]Has TOC:[/cyan] {'Yes' if result.has_toc else 'No'}",
            title="Detection Summary",
        )
        console.print(summary_panel)

        if not result.chapters:
            console.print("\n[yellow]No chapters detected.[/yellow]")
            return

        # Create table for chapters
        table = Table(title="Detected Chapters", show_header=True, header_style="bold cyan")
        table.add_column("#", style="dim", width=6)
        table.add_column("Title", style="white")
        table.add_column("File", style="dim")
        table.add_column("Level", justify="center", width=7)
        table.add_column("Method", style="cyan", width=12)
        table.add_column("Confidence", justify="center", width=12)

        for idx, chapter in enumerate(result.chapters, start=1):
            # Color code confidence
            conf_percent = f"{chapter.confidence * 100:.0f}%"
            if chapter.confidence >= 0.8:
                conf_color = "green"
            elif chapter.confidence >= 0.5:
                conf_color = "yellow"
            else:
                conf_color = "red"

            # Truncate title if too long
            title = chapter.title
            if len(title) > 50:
                title = title[:47] + "..."

            # Get filename without path
            filename = Path(chapter.file_path).name
            if chapter.html_id:
                filename += f"#{chapter.html_id}"

            table.add_row(
                str(idx),
                title,
                filename,
                str(chapter.level),
                chapter.detection_method,
                f"[{conf_color}]{conf_percent}[/{conf_color}]",
            )

        console.print(table)
        console.print()

    except click.Abort:
        raise
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {str(e)}")
        raise click.Abort()


if __name__ == "__main__":
    main()
