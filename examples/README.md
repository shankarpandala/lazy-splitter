# Examples

This directory contains example scripts showing how to use **Lazy Splitter's PDF tool**.

## Files

- **usage_example.py** - Demonstrates programmatic usage of the PDF splitter library

## Running Examples

Make sure you have lazy-splitter installed:

```bash
pip install lazy-splitter
# or for development
pip install -e .
```

Then modify the examples to point to your PDF files and run:

```bash
python examples/usage_example.py
```

## Example PDFs

For testing, you can use:
- Academic textbooks (often have clear chapter markers)
- Technical documentation
- Conference proceedings
- Any PDF with table of contents

## CLI Examples

Most users will prefer the CLI interface:

```bash
# Preview chapters
pdf-splitter preview your-book.pdf

# Split PDF
pdf-splitter split your-book.pdf

# Custom output
pdf-splitter split your-book.pdf -o chapters/ --strategy heuristic
```

See [docs/USAGE.md](../docs/USAGE.md) for comprehensive CLI examples.
