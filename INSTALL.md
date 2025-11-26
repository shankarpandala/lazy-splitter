# Installation Instructions

## For End Users

### Using pip (Recommended)

Once published to PyPI:

```bash
pip install lazy-splitter
```

### From GitHub

```bash
pip install git+https://github.com/shankarpandala/lazy-splitter.git
```

### From Source

```bash
# Clone the repository
git clone https://github.com/shankarpandala/lazy-splitter.git
cd lazy-splitter

# Install
pip install .
```

## For Developers

### Quick Setup

```bash
# Clone repository
git clone https://github.com/shankarpandala/lazy-splitter.git
cd lazy-splitter

# Run setup script
python setup_dev.py
```

### Manual Setup

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install in development mode with dev dependencies
pip install -e ".[dev]"
```

## Verify Installation

```bash
# Check version
pdf-splitter --version

# View help
pdf-splitter --help

# Run tests (developers only)
pytest
```

## System Requirements

- **Python:** 3.8 or higher
- **OS:** Windows, macOS, or Linux
- **Disk Space:** ~50 MB (including dependencies)
- **Memory:** Varies by PDF size (typically 100-500 MB)

## Dependencies

The tool will automatically install:
- PyMuPDF (fitz) - PDF manipulation
- Click - CLI framework
- Rich - Terminal formatting

## Troubleshooting

### Windows

If you get "python not found":
```bash
# Use py launcher
py -m pip install lazy-splitter
```

### macOS/Linux

If you get permission errors:
```bash
# Use --user flag
pip install --user lazy-splitter
```

### Virtual Environment Issues

If imports fail:
```bash
# Reinstall in virtual environment
deactivate
python -m venv venv --clear
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install lazy-splitter
```

### PyMuPDF Installation Issues

On some systems, PyMuPDF might need additional steps:

```bash
# Update pip first
pip install --upgrade pip

# Install PyMuPDF
pip install pymupdf

# Then install lazy-splitter
pip install lazy-splitter
```

## Upgrading

```bash
# Upgrade to latest version
pip install --upgrade lazy-splitter
```

## Uninstalling

```bash
pip uninstall lazy-splitter
```

## Platform-Specific Notes

### Windows
- Works on Windows 10/11
- Use PowerShell or Command Prompt
- Paths use backslashes: `C:\path\to\file.pdf`

### macOS
- Works on macOS 10.15+
- Install Xcode Command Line Tools if needed:
  ```bash
  xcode-select --install
  ```

### Linux
- Works on Ubuntu 20.04+, Debian, Fedora, etc.
- May need to install Python dev packages:
  ```bash
  # Ubuntu/Debian
  sudo apt-get install python3-dev
  
  # Fedora
  sudo dnf install python3-devel
  ```

## Next Steps

After installation:

1. Read the [Quick Start Guide](QUICKSTART.md)
2. Check [Usage Examples](docs/USAGE.md)
3. Join discussions on GitHub
4. Report issues or request features

## Getting Help

- **Documentation:** Check `docs/` folder
- **Issues:** GitHub Issues
- **Questions:** GitHub Discussions
