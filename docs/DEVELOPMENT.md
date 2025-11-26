# Development Setup Guide

Development guide for **Lazy Splitter** - a collection of intelligent file splitting tools.

## Prerequisites

- Python 3.8 or higher
- pip (Python package installer)
- Git

## Setup Instructions

### 1. Clone the repository

```bash
git clone https://github.com/shankarpandala/lazy-splitter.git
cd lazy-splitter
```

### 2. Create a virtual environment

**On Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**On macOS/Linux:**
```bash
python -m venv venv
source venv/bin/activate
```

### 3. Install development dependencies

```bash
pip install -e ".[dev]"
```

Or using Make:
```bash
make install-dev
```

### 4. Verify installation

```bash
pdf-splitter --version
```

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=pdf_splitter --cov-report=html

# Or use Make
make test
```

View coverage report by opening `htmlcov/index.html` in a browser.

## Code Quality

### Format code
```bash
black src/
# Or
make format
```

### Lint code
```bash
flake8 src/
# Or
make lint
```

### Type checking
```bash
mypy src/
```

## Building the Package

```bash
# Clean previous builds
make clean

# Build distribution packages
make build
```

This creates:
- `dist/pdf_chapter_splitter-X.Y.Z-py3-none-any.whl` (wheel)
- `dist/pdf-chapter-splitter-X.Y.Z.tar.gz` (source)

## Publishing to PyPI

### Test PyPI (recommended first)

1. Create account on [test.pypi.org](https://test.pypi.org)
2. Generate API token
3. Upload:

```bash
twine upload --repository testpypi dist/*
```

4. Test installation:

```bash
pip install --index-url https://test.pypi.org/simple/ pdf-chapter-splitter
```

### Production PyPI

1. Create account on [pypi.org](https://pypi.org)
2. Generate API token
3. Create `~/.pypirc`:

```ini
[pypi]
username = __token__
password = pypi-your-api-token-here
```

4. Upload:

```bash
make publish
# Or
twine upload dist/*
```

## Project Structure

```
pdf-chapter-splitter/
├── src/
│   └── pdf_splitter/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py          # CLI interface
│       ├── detector.py     # Chapter detection logic
│       ├── models.py       # Data models
│       └── splitter.py     # PDF splitting logic
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   └── test_detector.py
├── docs/
│   └── USAGE.md
├── .github/
│   └── workflows/
│       └── ci.yml
├── pyproject.toml          # Package configuration
├── README.md
├── LICENSE
├── CHANGELOG.md
└── requirements.txt
```

## Common Tasks

### Add a new dependency

1. Add to `pyproject.toml` under `dependencies`
2. Reinstall: `pip install -e ".[dev]"`

### Add a new CLI command

1. Add function in `src/pdf_splitter/cli.py`
2. Decorate with `@main.command()`
3. Test with `pdf-splitter <command-name>`

### Update version

1. Update version in `src/pdf_splitter/__init__.py`
2. Update version in `pyproject.toml`
3. Update `CHANGELOG.md`
4. Commit and tag: `git tag v0.X.Y`

## Troubleshooting

### Import errors after changes

```bash
pip install -e ".[dev]" --force-reinstall
```

### Tests not found

```bash
# Ensure pytest can find tests
export PYTHONPATH="${PYTHONPATH}:${PWD}/src"
pytest
```

### Windows-specific issues

If you encounter issues on Windows:
- Use `python` instead of `python3`
- Use backslashes in paths or raw strings
- Run terminal as Administrator if permission errors occur

## Getting Help

- Check existing issues on GitHub
- Read the documentation in `docs/`
- Open a new issue with detailed information
