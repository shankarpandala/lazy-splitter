# Changelog

All notable changes to Lazy Splitter will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2025-11-26

### Added - PDF Splitter
- Initial release of PDF chapter splitting tool
- Chapter detection using PDF bookmarks/TOC with hierarchy level selection
- Chapter detection using text analysis heuristics
- Hybrid detection strategy combining both methods
- CLI commands: `split` and `preview`
- Configurable detection sensitivity (low, medium, high)
- Bookmark level selection (parts, chapters, sections)
- Customizable output filename patterns
- Rich terminal output with tables and progress bars
- Metadata preservation in split PDFs
- Comprehensive error handling

### Features
- Smart chapter detection with multiple strategies
- Beautiful CLI interface with progress indicators
- Hierarchical bookmark navigation
- Flexible output options
- Cross-platform support (Windows, macOS, Linux)

### Coming Soon
- Video Splitter - Split videos by scenes, chapters, or silence
- Audio Splitter - Split audio files by silence or markers
- Document Splitter - Split Word docs, presentations, etc.
- Image Splitter - Split image collections and multi-page TIFFs

[0.1.0]: https://github.com/shankarpandala/lazy-splitter/releases/tag/v0.1.0
