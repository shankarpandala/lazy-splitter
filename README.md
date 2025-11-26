# Lazy Splitter

A collection of intelligent file splitting tools for the lazy developer. Split PDFs, EPUBs, and more with smart chapter detection.

## 🚀 Current Tools

### 📄 PDF Splitter
Intelligently detects chapters in PDF files and splits them into separate PDF files.

### 📚 EPUB Splitter
Intelligently detects chapters in EPUB files and splits them into separate EPUB files.

## Features

### PDF Splitter
- 🔍 **Smart Chapter Detection**: Automatically detects chapters using PDF bookmarks/TOC or text analysis
- 📑 **Multiple Detection Strategies**: 
  - Bookmark/TOC extraction (fastest and most reliable)
  - Heuristic text analysis (font size, heading patterns, "Chapter N" detection)
  - Hybrid approach (combines both methods)
- 📊 **Preview Mode**: See detected chapters before splitting
- 🎯 **Flexible Output**: Customizable output directory and filename patterns
- 🚀 **Progress Tracking**: Rich progress bars for large files
- ⚙️ **Configurable**: Fine-tune detection sensitivity and patterns

### EPUB Splitter
- 🔍 **Smart Chapter Detection**: Automatically detects chapters using native TOC, HTML structure, or manifest
- 📑 **Multiple Detection Strategies**: 
  - Native TOC extraction (EPUB 2 NCX and EPUB 3 navigation)
  - Structural analysis (HTML heading tags)
  - Manifest-based splitting (spine items)
  - Hybrid approach (combines all methods)
- 📊 **Preview Mode**: See detected chapters before splitting
- 🎯 **Flexible Output**: Customizable output directory and filename patterns
- 📦 **Resource Handling**: Automatically copies referenced images, CSS, and fonts
- ⚙️ **Configurable**: Fine-tune detection sensitivity and TOC levels

## Installation

### From PyPI (recommended)

```bash
pip install lazy-splitter
```

### From Source

```bash
git clone https://github.com/shankarpandala/lazy-splitter.git
cd lazy-splitter
pip install -e .
```

## Usage

### PDF Splitter

#### Split a PDF by chapters

```bash
pdf-splitter split input.pdf
```

#### Preview detected chapters without splitting

```bash
pdf-splitter preview input.pdf
```

#### Specify output directory

```bash
pdf-splitter split input.pdf -o output_dir
```

#### Choose detection strategy

```bash
# Use bookmarks only (fastest)
pdf-splitter split input.pdf --strategy bookmarks

# Use text analysis only (when bookmarks are missing)
pdf-splitter split input.pdf --strategy heuristic

# Use both methods (default)
pdf-splitter split input.pdf --strategy hybrid
```

#### Customize output filename pattern

```bash
pdf-splitter split input.pdf --pattern "{index:02d}_{title}.pdf"
```

### EPUB Splitter

#### Split an EPUB by chapters

```bash
epub-splitter split ebook.epub
```

#### Preview detected chapters without splitting

```bash
epub-splitter preview ebook.epub
```

#### Specify output directory

```bash
epub-splitter split ebook.epub -o output_dir
```

#### Choose detection strategy

```bash
# Use native TOC only (fastest and most reliable)
epub-splitter split ebook.epub --strategy native

# Use HTML structure analysis (when TOC is missing)
epub-splitter split ebook.epub --strategy structural

# Use manifest-based splitting (one chapter per file)
epub-splitter split ebook.epub --strategy manifest

# Use hybrid approach (default)
epub-splitter split ebook.epub --strategy hybrid
```

#### Customize output filename pattern

```bash
epub-splitter split ebook.epub --pattern "{index:02d}_{title}.epub"
```

## Examples

### PDF Examples

```bash
# Basic usage
pdf-splitter split textbook.pdf

# Preview chapters first
pdf-splitter preview textbook.pdf

# Custom output location
pdf-splitter split textbook.pdf -o chapters/

# Force heuristic detection (for PDFs without bookmarks)
pdf-splitter split textbook.pdf --strategy heuristic --sensitivity high
```

### EPUB Examples

```bash
# Basic usage
epub-splitter split novel.epub

# Preview chapters first
epub-splitter preview novel.epub

# Custom output location
epub-splitter split novel.epub -o chapters/

# Use structural detection (for EPUBs without TOC)
epub-splitter split novel.epub --strategy structural --sensitivity high

# Split by TOC level 2 (chapters instead of parts)
epub-splitter split textbook.epub --toc-level 2
```

## How It Works

### PDF Splitter

1. **Bookmark/TOC Extraction**: First tries to extract chapter information from PDF bookmarks or table of contents
2. **Text Analysis Fallback**: If bookmarks are unavailable, analyzes text for:
   - Font size changes (larger fonts often indicate headings)
   - Common chapter patterns ("Chapter 1", "CHAPTER ONE", etc.)
   - Page breaks combined with heading-like text
3. **Smart Splitting**: Creates individual PDF files for each detected chapter with preserved formatting and metadata

### EPUB Splitter

1. **Native TOC Extraction**: First tries to extract chapter information from EPUB navigation (nav.xhtml or toc.ncx)
2. **Structural Analysis Fallback**: If TOC is unavailable, analyzes HTML structure for:
   - Heading tags (h1, h2, h3) based on sensitivity level
   - Semantic HTML structure
   - Title extraction from content
3. **Manifest-based Fallback**: Uses EPUB spine/manifest to create one chapter per content file
4. **Smart Splitting**: Creates individual EPUB files for each detected chapter with:
   - Preserved metadata and styling
   - Automatically copied resources (images, CSS, fonts)
   - Valid EPUB structure with regenerated manifest and spine

## Requirements

- Python 3.8+
- PyMuPDF (for PDF manipulation)
- EbookLib (for EPUB manipulation)
- lxml (for HTML/XML parsing)
- Click (for CLI interface)
- Rich (for beautiful terminal output)

## Development

```bash
# Install with development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black src/

# Type checking
mypy src/
```

## License

MIT License - see LICENSE file for details

## 🗺️ Roadmap

### ✅ Completed
- ✅ **PDF Splitter** - Split PDFs by chapters with smart detection
- ✅ **EPUB Splitter** - Split EPUBs by chapters with TOC and structural analysis

### Coming Soon
- 🎬 **Video Splitter** - Split videos by scenes, chapters, or silence detection
- 🎵 **Audio Splitter** - Split audio files by silence, chapters, or time intervals
- 📊 **Document Splitter** - Split Word docs, presentations, and more
- 🖼️ **Image Splitter** - Split image collections and multi-page TIFFs

## Contributing

Contributions are welcome! We're building a suite of intelligent splitting tools. Please feel free to submit a Pull Request.

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
