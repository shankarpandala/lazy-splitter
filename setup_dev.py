#!/usr/bin/env python
"""
Setup script for quick development environment setup.
Run this script to set up your development environment.
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd, description):
    """Run a shell command and handle errors."""
    print(f"\n{'='*60}")
    print(f"📦 {description}")
    print(f"{'='*60}")
    try:
        subprocess.run(cmd, check=True, shell=True)
        print(f"✓ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ {description} failed with error code {e.returncode}")
        return False


def main():
    """Main setup function."""
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║                                                          ║
    ║        PDF Chapter Splitter - Development Setup         ║
    ║                                                          ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required!")
        print(f"   Current version: {sys.version}")
        sys.exit(1)
    
    print(f"✓ Python version: {sys.version.split()[0]}")
    
    # Upgrade pip
    if not run_command(
        f"{sys.executable} -m pip install --upgrade pip",
        "Upgrading pip"
    ):
        print("⚠ Warning: pip upgrade failed, continuing anyway...")
    
    # Install package in development mode
    if not run_command(
        f"{sys.executable} -m pip install -e \".[dev]\"",
        "Installing package with development dependencies"
    ):
        print("❌ Installation failed!")
        sys.exit(1)
    
    # Run tests to verify installation
    print("\n" + "="*60)
    print("🧪 Running tests to verify installation")
    print("="*60)
    result = subprocess.run([sys.executable, "-m", "pytest", "-v"], capture_output=False)
    
    if result.returncode == 0:
        print("\n✓ All tests passed!")
    else:
        print("\n⚠ Some tests failed (this is normal if you haven't added test PDFs yet)")
    
    # Final instructions
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║                                                          ║
    ║                Setup Complete! 🎉                        ║
    ║                                                          ║
    ╚══════════════════════════════════════════════════════════╝
    
    Next steps:
    
    1. Try the CLI:
       $ pdf-splitter --help
       $ pdf-splitter preview your-file.pdf
       $ pdf-splitter split your-file.pdf
    
    2. Run tests:
       $ pytest
       $ pytest --cov=pdf_splitter --cov-report=html
    
    3. Code quality:
       $ black src/          # Format code
       $ flake8 src/         # Lint code
       $ mypy src/           # Type check
    
    4. Read the documentation:
       - README.md           - Project overview
       - docs/USAGE.md       - Usage examples
       - docs/DEVELOPMENT.md - Development guide
       - CONTRIBUTING.md     - Contribution guidelines
    
    Happy coding! 🚀
    """)


if __name__ == "__main__":
    main()
