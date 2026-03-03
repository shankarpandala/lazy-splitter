"""Allow running lazy-splitter as ``python -m lazy_splitter``.

This module is executed when the package is invoked directly::

    python -m lazy_splitter --help
    python -m lazy_splitter split document.pdf
    python -m lazy_splitter info book.epub
"""

from __future__ import annotations

from lazy_splitter.cli import main

if __name__ == "__main__":
    main()
