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

## Branching and Promotion Flow

The repository uses a staged promotion model:

- `dev`: integration branch for feature and bug-fix PRs
- `qa`: pre-release validation branch (beta package publishing)
- `release`: production-ready branch (stable package publishing)
- `main`: should be kept aligned with `release` and not used for direct feature work

Recommended merge path:

1. `feature/*` -> `dev`
2. `dev` -> `qa`
3. `qa` -> `release`
4. `release` -> `main`

Use branch protection rules on `dev`, `qa`, `release`, and `main` to require PRs and passing CI checks.

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

## Automated Publishing via GitHub Actions

The CI workflow is configured so that:

- PRs and pushes to `main`, `dev`, `qa`, and `release` run tests and lint checks.
- Pushes to `dev` publish an alpha package to PyPI using `<base_version>a<run_number>`.
- Pushes to `qa` publish a beta package to PyPI using `<base_version>b<run_number>`.
- Pushes to `release` publish stable packages to PyPI.

Required repository secrets:

- `PYPI_API_TOKEN` for alpha, beta, and stable publishing

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
