# PDF Splitter - Usage Examples

Part of the **Lazy Splitter** suite of intelligent file splitting tools.

## Installation

### Using pip (PyPI)

```bash
pip install lazy-splitter
```

### From source

```bash
git clone https://github.com/shankarpandala/lazy-splitter.git
cd lazy-splitter
pip install -e .
```

## Basic Usage

### Split a PDF

The simplest way to split a PDF:

```bash
pdf-splitter split mybook.pdf
```

This will:
1. Analyze `mybook.pdf`
2. Detect chapters
3. Create a folder `mybook_chapters/`
4. Save each chapter as a separate PDF

### Preview Chapters First

Before splitting, you can preview what chapters will be detected:

```bash
pdf-splitter preview mybook.pdf
```

This shows:
- Number of chapters found
- Chapter titles
- Page ranges
- Detection confidence scores

## Advanced Usage

### Custom Output Directory

```bash
pdf-splitter split mybook.pdf -o /path/to/output
```

### Detection Strategies

**Bookmarks only** (fastest, most reliable if bookmarks exist):
```bash
pdf-splitter split mybook.pdf --strategy bookmarks
```

**Text analysis only** (for PDFs without bookmarks):
```bash
pdf-splitter split mybook.pdf --strategy heuristic
```

**Hybrid** (default - tries bookmarks first, falls back to heuristics):
```bash
pdf-splitter split mybook.pdf --strategy hybrid
```

### Sensitivity Control

For heuristic detection, control how aggressively to detect chapters:

```bash
# Conservative - only very clear chapter markers
pdf-splitter split mybook.pdf --sensitivity low

# Balanced (default)
pdf-splitter split mybook.pdf --sensitivity medium

# Aggressive - detects more potential chapters
pdf-splitter split mybook.pdf --sensitivity high
```

### Custom Filename Patterns

Control how output files are named:

```bash
# Default: 01_Chapter_Title.pdf, 02_Another_Chapter.pdf
pdf-splitter split mybook.pdf

# Just numbers: 01.pdf, 02.pdf
pdf-splitter split mybook.pdf --pattern "{index:02d}.pdf"

# With page ranges: Chapter_1_pages_1-25.pdf
pdf-splitter split mybook.pdf --pattern "Chapter_{index}_pages_{start}-{end}.pdf"

# Title only: Introduction.pdf, Methods.pdf
pdf-splitter split mybook.pdf --pattern "{title}.pdf"
```

Available placeholders:
- `{index}` - Chapter number (1, 2, 3...)
- `{index:02d}` - Chapter number padded (01, 02, 03...)
- `{title}` - Chapter title (sanitized for filenames)
- `{start}` - First page number
- `{end}` - Last page number
- `{pages}` - Number of pages in chapter

### Don't Preserve Metadata

By default, PDF metadata is copied to split files. To skip this:

```bash
pdf-splitter split mybook.pdf --no-metadata
```

## Real-World Examples

### Academic Textbook

```bash
# Preview first to check detection quality
pdf-splitter preview textbook.pdf --strategy hybrid

# Split with high sensitivity to catch all chapter variations
pdf-splitter split textbook.pdf --sensitivity high -o textbook_chapters/
```

### Technical Manual

```bash
# Manuals often have detailed bookmarks
pdf-splitter split manual.pdf --strategy bookmarks -o manual_sections/
```

### Scanned Book (no bookmarks)

```bash
# Use heuristic detection with medium sensitivity
pdf-splitter split scanned_book.pdf --strategy heuristic --sensitivity medium
```

### Conference Proceedings

```bash
# Each paper might be a "chapter"
pdf-splitter split proceedings.pdf --pattern "Paper_{index:03d}_{title}.pdf" -o papers/
```

## Troubleshooting

### No chapters detected

If no chapters are found:
1. Try `--strategy heuristic` (PDF might not have bookmarks)
2. Increase sensitivity: `--sensitivity high`
3. Use `preview` command to see what's being detected
4. The PDF might truly have no chapter markers

### Too many false chapters detected

If detecting too many chapters:
1. Try `--strategy bookmarks` (if bookmarks exist)
2. Decrease sensitivity: `--sensitivity low`
3. Verify PDF structure with `preview` command

### Wrong chapter titles

If using heuristic detection, titles are extracted from text. They might not be perfect. You can:
1. Use bookmarks strategy if available
2. Manually rename files after splitting
3. Use a simple numeric pattern: `--pattern "{index:02d}.pdf"`

## Getting Help

```bash
# General help
pdf-splitter --help

# Help for specific command
pdf-splitter split --help
pdf-splitter preview --help

# Version info
pdf-splitter --version
```
