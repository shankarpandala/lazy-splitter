"""CLI interface for PDF chapter splitter."""

from pathlib import Path
from typing import Optional
import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel

from pdf_splitter.detector import ChapterDetector
from pdf_splitter.splitter import PDFSplitter
from pdf_splitter import __version__


console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="pdf-splitter")
def main() -> None:
    """
    PDF Chapter Splitter - Intelligently detect and split PDF chapters.
    
    Detects chapters using bookmarks/TOC or text analysis heuristics,
    then splits the PDF into separate files.
    """
    pass


@main.command()
@click.argument('pdf_file', type=click.Path(exists=True, path_type=Path))
@click.option(
    '-o', '--output-dir',
    type=click.Path(path_type=Path),
    default=None,
    help='Output directory for split PDFs (default: <pdf_name>_chapters/)'
)
@click.option(
    '--strategy',
    type=click.Choice(['bookmarks', 'heuristic', 'hybrid'], case_sensitive=False),
    default='hybrid',
    help='Chapter detection strategy (default: hybrid)'
)
@click.option(
    '--sensitivity',
    type=click.Choice(['low', 'medium', 'high'], case_sensitive=False),
    default='medium',
    help='Detection sensitivity for heuristic analysis (default: medium)'
)
@click.option(
    '--bookmark-level',
    type=int,
    default=1,
    help='Bookmark hierarchy level to use for splitting (default: 1). Use 1 for parts, 2 for chapters, 3 for sections, etc.'
)
@click.option(
    '--pattern',
    type=str,
    default='{index:02d}_{title}.pdf',
    help='Filename pattern for output files (default: {index:02d}_{title}.pdf)'
)
@click.option(
    '--no-metadata',
    is_flag=True,
    help='Do not preserve PDF metadata in split files'
)
def split(
    pdf_file: Path,
    output_dir: Optional[Path],
    strategy: str,
    sensitivity: str,
    bookmark_level: int,
    pattern: str,
    no_metadata: bool
) -> None:
    """
    Split a PDF file by detected chapters.
    
    PDF_FILE: Path to the PDF file to split
    
    Examples:
    
        pdf-splitter split textbook.pdf
        
        pdf-splitter split textbook.pdf -o chapters/
        
        pdf-splitter split textbook.pdf --strategy heuristic --sensitivity high
    """
    try:
        # Validate PDF file
        if not pdf_file.suffix.lower() == '.pdf':
            console.print("[red]Error: Input file must be a PDF[/red]")
            raise click.Abort()
        
        # Set default output directory
        if output_dir is None:
            output_dir = pdf_file.parent / f"{pdf_file.stem}_chapters"
        
        console.print(f"\n[bold cyan]PDF Chapter Splitter[/bold cyan] v{__version__}\n")
        console.print(f"[dim]Input:[/dim] {pdf_file}")
        console.print(f"[dim]Output:[/dim] {output_dir}")
        console.print(f"[dim]Strategy:[/dim] {strategy}")
        console.print(f"[dim]Sensitivity:[/dim] {sensitivity}")
        if strategy in ['bookmarks', 'hybrid']:
            console.print(f"[dim]Bookmark Level:[/dim] {bookmark_level}")
        console.print()
        
        # Detect chapters
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Analyzing PDF and detecting chapters...", total=None)
            
            detector = ChapterDetector(sensitivity=sensitivity)
            result = detector.detect(pdf_file, strategy=strategy, bookmark_level=bookmark_level)
            
            progress.update(task, completed=True)
        
        # Display detection results
        console.print(f"\n[green]✓[/green] Found {result.chapter_count} chapter(s)\n")
        
        # Show chapters in a table
        table = Table(title="Detected Chapters", show_header=True, header_style="bold magenta")
        table.add_column("#", style="dim", width=4)
        table.add_column("Title", style="cyan")
        table.add_column("Pages", justify="right")
        table.add_column("Page Range", justify="center", style="dim")
        table.add_column("Confidence", justify="center")
        
        for i, chapter in enumerate(result.chapters, start=1):
            confidence_str = f"{chapter.confidence:.0%}"
            if chapter.confidence >= 0.8:
                confidence_color = "green"
            elif chapter.confidence >= 0.6:
                confidence_color = "yellow"
            else:
                confidence_color = "red"
            
            table.add_row(
                str(i),
                chapter.title,
                str(chapter.page_count),
                f"{chapter.start_page}-{chapter.end_page}",
                f"[{confidence_color}]{confidence_str}[/{confidence_color}]"
            )
        
        console.print(table)
        console.print()
        
        # Ask for confirmation if using fallback or low confidence chapters
        if result.strategy_used == "fallback":
            console.print("[yellow]⚠ Warning: No chapters detected. Treating entire document as one chapter.[/yellow]")
            if not click.confirm("\nProceed with split?"):
                console.print("[dim]Split cancelled.[/dim]")
                return
        
        # Split PDF
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Splitting PDF into chapters...", total=None)
            
            splitter = PDFSplitter(output_dir, filename_pattern=pattern)
            created_files = splitter.split(
                pdf_file,
                result.chapters,
                preserve_metadata=not no_metadata
            )
            
            progress.update(task, completed=True)
        
        # Display success message
        console.print(f"\n[green]✓ Successfully created {len(created_files)} PDF file(s)[/green]")
        console.print(f"[dim]Output directory:[/dim] {output_dir}\n")
        
        # List created files
        if len(created_files) <= 10:
            for file_path in created_files:
                console.print(f"  [dim]•[/dim] {file_path.name}")
        else:
            console.print(f"  [dim]... {len(created_files)} files created[/dim]")
        
        console.print()
        
    except Exception as e:
        console.print(f"\n[red]Error: {str(e)}[/red]\n")
        raise click.Abort()


@main.command()
@click.argument('pdf_file', type=click.Path(exists=True, path_type=Path))
@click.option(
    '--strategy',
    type=click.Choice(['bookmarks', 'heuristic', 'hybrid'], case_sensitive=False),
    default='hybrid',
    help='Chapter detection strategy (default: hybrid)'
)
@click.option(
    '--sensitivity',
    type=click.Choice(['low', 'medium', 'high'], case_sensitive=False),
    default='medium',
    help='Detection sensitivity for heuristic analysis (default: medium)'
)
@click.option(
    '--bookmark-level',
    type=int,
    default=1,
    help='Bookmark hierarchy level to use for detection (default: 1). Use 1 for parts, 2 for chapters, 3 for sections, etc.'
)
def preview(
    pdf_file: Path,
    strategy: str,
    sensitivity: str,
    bookmark_level: int
) -> None:
    """
    Preview detected chapters without splitting the PDF.
    
    PDF_FILE: Path to the PDF file to analyze
    
    Examples:
    
        pdf-splitter preview textbook.pdf
        
        pdf-splitter preview textbook.pdf --strategy bookmarks
    """
    try:
        # Validate PDF file
        if not pdf_file.suffix.lower() == '.pdf':
            console.print("[red]Error: Input file must be a PDF[/red]")
            raise click.Abort()
        
        console.print(f"\n[bold cyan]PDF Chapter Splitter[/bold cyan] v{__version__}\n")
        console.print(f"[dim]File:[/dim] {pdf_file}")
        console.print(f"[dim]Strategy:[/dim] {strategy}")
        console.print(f"[dim]Sensitivity:[/dim] {sensitivity}")
        if strategy in ['bookmarks', 'hybrid']:
            console.print(f"[dim]Bookmark Level:[/dim] {bookmark_level}")
        console.print()
        
        # Detect chapters
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Analyzing PDF and detecting chapters...", total=None)
            
            detector = ChapterDetector(sensitivity=sensitivity)
            result = detector.detect(pdf_file, strategy=strategy, bookmark_level=bookmark_level)
            
            progress.update(task, completed=True)
        
        # Display results summary
        summary_panel = Panel(
            result.get_summary(),
            title="Detection Summary",
            border_style="cyan"
        )
        console.print(summary_panel)
        console.print()
        
        # Show chapters in a table
        if result.chapters:
            table = Table(title="Detected Chapters", show_header=True, header_style="bold magenta")
            table.add_column("#", style="dim", width=4)
            table.add_column("Title", style="cyan")
            table.add_column("Pages", justify="right")
            table.add_column("Page Range", justify="center", style="dim")
            table.add_column("Method", justify="center")
            table.add_column("Confidence", justify="center")
            
            for i, chapter in enumerate(result.chapters, start=1):
                confidence_str = f"{chapter.confidence:.0%}"
                if chapter.confidence >= 0.8:
                    confidence_color = "green"
                elif chapter.confidence >= 0.6:
                    confidence_color = "yellow"
                else:
                    confidence_color = "red"
                
                method_color = "green" if chapter.detection_method == "bookmark" else "yellow"
                
                table.add_row(
                    str(i),
                    chapter.title,
                    str(chapter.page_count),
                    f"{chapter.start_page}-{chapter.end_page}",
                    f"[{method_color}]{chapter.detection_method}[/{method_color}]",
                    f"[{confidence_color}]{confidence_str}[/{confidence_color}]"
                )
            
            console.print(table)
            console.print()
        else:
            console.print("[yellow]No chapters detected.[/yellow]\n")
        
        # Show recommendations
        if not result.has_bookmarks and strategy != "heuristic":
            console.print("[dim]💡 Tip: This PDF has no bookmarks. Try --strategy heuristic for better results.[/dim]\n")
        
    except Exception as e:
        console.print(f"\n[red]Error: {str(e)}[/red]\n")
        raise click.Abort()


if __name__ == '__main__':
    main()
