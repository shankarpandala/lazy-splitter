# Getting Started with Lazy Splitter

## Overview

**Lazy Splitter** is a collection of intelligent file splitting tools. This guide focuses on the **PDF Splitter** tool.

> **Coming Soon:** Video Splitter, Audio Splitter, Document Splitter, and more!

## ⚡ Quick Start - PDF Splitter (3 steps)

### 1. Install
```bash
pip install -e .
```

### 2. Preview
```bash
pdf-splitter preview your-book.pdf
```

### 3. Split
```bash
pdf-splitter split your-book.pdf
```

That's it! Your chapters are now in `your-book_chapters/`

---

## 📚 What You Need to Know

### Commands

**`pdf-splitter preview <file>`**
- Shows detected chapters without splitting
- Use this first to check results

**`pdf-splitter split <file>`**
- Splits PDF into separate chapter files
- Creates output directory automatically

### Key Options

| Option | Description | Example |
|--------|-------------|---------|
| `-o, --output-dir` | Custom output location | `-o chapters/` |
| `--strategy` | Detection method | `--strategy bookmarks` |
| `--sensitivity` | Detection sensitivity | `--sensitivity high` |
| `--pattern` | Filename pattern | `--pattern "{index}_{title}.pdf"` |

### Detection Strategies

- **`bookmarks`** - Use PDF table of contents (fastest)
- **`heuristic`** - Analyze text patterns (when no TOC)
- **`hybrid`** - Try bookmarks, then heuristic (default)

### Sensitivity Levels

- **`low`** - Only obvious chapters
- **`medium`** - Balanced (default)
- **`high`** - Detect more potential chapters

---

## 💡 Common Use Cases

### Academic Textbook
```bash
# Preview first
pdf-splitter preview textbook.pdf

# Split with default settings
pdf-splitter split textbook.pdf
```

### PDF Without Bookmarks
```bash
# Use text analysis
pdf-splitter split book.pdf --strategy heuristic --sensitivity high
```

### Custom Organization
```bash
# Number-only filenames
pdf-splitter split book.pdf --pattern "{index:02d}.pdf" -o numbered/

# Include page ranges
pdf-splitter split book.pdf --pattern "Chapter_{index}_pages_{start}-{end}.pdf"
```

---

## 🎓 Learning Path

1. **Start Here:** [QUICKSTART.md](QUICKSTART.md)
2. **Deep Dive:** [docs/USAGE.md](docs/USAGE.md)
3. **Examples:** [examples/](examples/)
4. **Development:** [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)

---

## 🔧 For Developers

### Setup Development Environment
```bash
python setup_dev.py
```

### Run Tests
```bash
pytest --cov=pdf_splitter
```

### Code Quality
```bash
make format  # Format code
make lint    # Check code quality
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

---

## ❓ Troubleshooting

**No chapters detected?**
- Try `--strategy heuristic`
- Increase sensitivity: `--sensitivity high`
- Use `preview` to check what's detected

**Too many chapters?**
- Try `--strategy bookmarks`
- Decrease sensitivity: `--sensitivity low`

**Wrong chapter titles?**
- Use simple pattern: `--pattern "{index}.pdf"`
- Rename files after splitting

---

## 📖 Documentation Index

- **[README.md](README.md)** - Project overview
- **[QUICKSTART.md](QUICKSTART.md)** - 5-minute guide
- **[INSTALL.md](INSTALL.md)** - Installation help
- **[docs/USAGE.md](docs/USAGE.md)** - Comprehensive examples
- **[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)** - Developer guide
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - How to contribute
- **[PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)** - Architecture details
- **[CHANGELOG.md](CHANGELOG.md)** - Version history

---

## 🚀 What's Next?

- [ ] Try it with your own PDFs
- [ ] Experiment with different strategies
- [ ] Star the repo if you find it useful
- [ ] Report bugs or request features
- [ ] Contribute improvements

**Happy splitting! 📄✂️**
