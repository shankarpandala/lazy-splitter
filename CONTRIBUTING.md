# Contributing to Lazy Splitter

Thank you for considering contributing to Lazy Splitter! This document provides guidelines and instructions for contributing.

## About Lazy Splitter

Lazy Splitter is a collection of intelligent file splitting tools:
- **PDF Splitter** - Split PDFs by chapters (currently available)
- **Video Splitter** - Coming soon
- **Audio Splitter** - Coming soon
- **Document Splitter** - Coming soon

## Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/shankarpandala/lazy-splitter.git
   cd lazy-splitter
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   # On Windows
   venv\Scripts\activate
   # On Unix/macOS
   source venv/bin/activate
   ```

3. **Install in development mode**
   ```bash
   pip install -e ".[dev]"
   ```

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=pdf_splitter --cov-report=html

# Run specific test file
pytest tests/test_detector.py
```

## Code Style

We use:
- **Black** for code formatting
- **Flake8** for linting
- **MyPy** for type checking

Run these before committing:

```bash
# Format code
black src/

# Lint
flake8 src/

# Type check
mypy src/
```

## Making Changes

1. Create a new branch for your feature/fix
2. Make your changes
3. Add or update tests as needed
4. Ensure all tests pass
5. Format and lint your code
6. Commit with a clear message
7. Push and create a pull request

## Areas for Contribution

- **Additional detection strategies**: Improve chapter detection algorithms
- **Support for more patterns**: Add regex patterns for different chapter styles
- **Performance optimization**: Speed up processing for large PDFs
- **Better error handling**: Improve error messages and recovery
- **Documentation**: Improve docs, add examples
- **Tests**: Increase test coverage

## Questions?

Feel free to open an issue for any questions or clarifications!
