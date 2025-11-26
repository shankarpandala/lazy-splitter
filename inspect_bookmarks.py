"""Quick script to inspect PDF bookmark structure."""

import fitz  # PyMuPDF
from pathlib import Path

pdf_path = Path("examples/mml-book.pdf")
doc = fitz.open(pdf_path)

print(f"Total pages: {len(doc)}")
print(f"\nBookmark/TOC structure:")
print("=" * 80)

toc = doc.get_toc()
for level, title, page in toc[:50]:  # Show first 50 entries
    indent = "  " * (level - 1)
    print(f"{indent}Level {level}: '{title}' -> Page {page}")

print(f"\n... (showing first 50 of {len(toc)} total bookmarks)")
print("=" * 80)

# Count by level
level_counts = {}
for level, title, page in toc:
    level_counts[level] = level_counts.get(level, 0) + 1

print("\nBookmark levels summary:")
for level in sorted(level_counts.keys()):
    print(f"  Level {level}: {level_counts[level]} bookmarks")

doc.close()
