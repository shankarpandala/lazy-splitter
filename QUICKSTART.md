# Quick Start Guide

Get started with Lazy Splitter's PDF tool in under 5 minutes!

## Installation

```bash
pip install lazy-splitter
```

## Usage

### 1. Preview chapters in your PDF

```bash
pdf-splitter preview mybook.pdf
```

### 2. Split the PDF

```bash
pdf-splitter split mybook.pdf
```

That's it! Your chapters will be in a folder called `mybook_chapters/`

## Common Options

```bash
# Custom output folder
pdf-splitter split mybook.pdf -o chapters/

# If PDF has no bookmarks, use text analysis
pdf-splitter split mybook.pdf --strategy heuristic

# Increase detection sensitivity
pdf-splitter split mybook.pdf --sensitivity high
```

For more examples, see [docs/USAGE.md](docs/USAGE.md)
