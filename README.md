# Lazy Splitter

A collection of intelligent file splitting tools for the lazy developer. Currently featuring PDF chapter detection and splitting, with more formats coming soon.

## 🚀 Current Tools

### 📄 PDF Splitter
Intelligently detects chapters in PDF files and splits them into separate PDF files.

## Features

- 🔍 **Smart Chapter Detection**: Automatically detects chapters using PDF bookmarks/TOC or text analysis
- 📑 **Multiple Detection Strategies**: 
  - Bookmark/TOC extraction (fastest and most reliable)
  - Heuristic text analysis (font size, heading patterns, "Chapter N" detection)
  - Hybrid approach (combines both methods)
- 📊 **Preview Mode**: See detected chapters before splitting
- 🎯 **Flexible Output**: Customizable output directory and filename patterns
- 🚀 **Progress Tracking**: Rich progress bars for large files
- ⚙️ **Configurable**: Fine-tune detection sensitivity and patterns

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

### Split a PDF by chapters

```bash
pdf-splitter split input.pdf
```

### Preview detected chapters without splitting

```bash
pdf-splitter preview input.pdf
```

### Specify output directory

```bash
pdf-splitter split input.pdf -o output_dir
```

### Choose detection strategy

```bash
# Use bookmarks only (fastest)
pdf-splitter split input.pdf --strategy bookmarks

# Use text analysis only (when bookmarks are missing)
pdf-splitter split input.pdf --strategy heuristic

# Use both methods (default)
pdf-splitter split input.pdf --strategy hybrid
```

### Customize output filename pattern

```bash
pdf-splitter split input.pdf --pattern "{index:02d}_{title}.pdf"
```

## Examples

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

## How It Works

1. **Bookmark/TOC Extraction**: First tries to extract chapter information from PDF bookmarks or table of contents
2. **Text Analysis Fallback**: If bookmarks are unavailable, analyzes text for:
   - Font size changes (larger fonts often indicate headings)
   - Common chapter patterns ("Chapter 1", "CHAPTER ONE", etc.)
   - Page breaks combined with heading-like text
3. **Smart Splitting**: Creates individual PDF files for each detected chapter with preserved formatting and metadata

## Requirements

- Python 3.8+
- PyMuPDF (for PDF manipulation)
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

### Coming Soon
- 🎬 **Video Splitter** - Split videos by scenes, chapters, or silence detection
- 🎵 **Audio Splitter** - Split audio files by silence, chapters, or time intervals
- 📊 **Document Splitter** - Split Word docs, presentations, and more
- 🖼️ **Image Splitter** - Split image collections and multi-page TIFFs

## Contributing

Contributions are welcome! We're building a suite of intelligent splitting tools. Please feel free to submit a Pull Request.

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
