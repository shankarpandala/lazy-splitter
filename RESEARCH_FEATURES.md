# Lazy Splitter - Comprehensive Feature Catalog

> Deep research into all additional features and capabilities that can be added to the project.
> Generated: 2026-03-01 | Current Version: 0.2.0 (Alpha)

---

## Table of Contents

1. [PDF Splitter Enhancements](#1-pdf-splitter-enhancements)
2. [EPUB Splitter Enhancements](#2-epub-splitter-enhancements)
3. [Video Splitter (New Module)](#3-video-splitter-new-module)
4. [Audio Splitter (New Module)](#4-audio-splitter-new-module)
5. [Document Splitter (New Module)](#5-document-splitter-new-module)
6. [Image Splitter (New Module)](#6-image-splitter-new-module)
7. [AI/ML-Powered Features](#7-aiml-powered-features)
8. [Unified CLI & TUI](#8-unified-cli--tui)
9. [Merge/Join - Reverse Operations](#9-mergejoin---reverse-operations)
10. [Batch Processing & Automation](#10-batch-processing--automation)
11. [Format Conversion](#11-format-conversion)
12. [Cloud & Web Integration](#12-cloud--web-integration)
13. [Developer Experience & API](#13-developer-experience--api)
14. [Cross-cutting Platform Features](#14-cross-cutting-platform-features)

---

## 1. PDF Splitter Enhancements

### 1.1 Advanced Splitting Strategies

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Split by page range** | Allow users to specify arbitrary page ranges (e.g., `1-5,10-15,20-end`) | PyMuPDF `insert_pdf(from_page, to_page)` |
| **Split by page count** | Split into equal-sized chunks of N pages | Simple arithmetic division |
| **Split by file size** | Split so each output PDF is under a target file size (e.g., 10MB) | Iterative page addition with size checks |
| **Split by blank pages** | Detect and split at blank/separator pages | PyMuPDF page pixel analysis, `page.get_pixmap()` |
| **Split by content type** | Separate text-heavy pages from image-heavy pages | Analyze text block density vs image block ratio |
| **Split every N pages** | Simple N-page interval splitting | Straightforward page iteration |
| **Split by regex pattern** | User-supplied regex for chapter heading detection | Extend `CHAPTER_PATTERNS` to accept user patterns |
| **Split at page breaks** | Detect logical page breaks in continuous documents | Analyze whitespace patterns and content flow |
| **Even/odd page extraction** | Extract only even or odd pages | Simple page index filtering |

### 1.2 Password & Security

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Password-protected PDF support** | Decrypt and split password-protected PDFs | `fitz.open(path, password=...)` - PyMuPDF native support |
| **Re-encrypt split files** | Apply password protection to output files | `doc.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=..., owner_pw=...)` |
| **Permission preservation** | Maintain original PDF permissions (print, copy, etc.) | PyMuPDF permission flags |
| **Digital signature handling** | Detect and warn about signed PDFs (signatures invalidated by splitting) | Check for signature form fields |
| **Redaction support** | Redact sensitive content before or during splitting | `page.add_redact_annot()` + `page.apply_redactions()` |

### 1.3 OCR & Scanned Document Support

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **OCR integration** | Extract text from scanned/image-based PDFs for chapter detection | `pytesseract` or `easyocr` with PyMuPDF image extraction |
| **OCR language support** | Multi-language OCR for international documents | Tesseract language packs (`-l eng+fra+deu`) |
| **OCR confidence scoring** | Report OCR quality to adjust detection thresholds | Tesseract confidence scores per word/line |
| **Hybrid text+OCR** | Use native text where available, OCR for image-only pages | Page-by-page text extraction check, OCR fallback |
| **OCR caching** | Cache OCR results to avoid re-processing on subsequent runs | Hash-based file cache with `shelve` or SQLite |

### 1.4 Content & Metadata

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Annotation preservation** | Preserve highlights, comments, sticky notes in split files | PyMuPDF annotation handling (`page.annots()`) |
| **Form field preservation** | Maintain interactive form fields across split files | PyMuPDF widget handling |
| **Link preservation** | Fix internal cross-references after splitting | Remap link destinations in `page.get_links()` |
| **Embedded file extraction** | Extract files embedded within PDFs (attachments) | `doc.embfile_names()` + `doc.embfile_get()` |
| **TOC generation** | Generate a table of contents for each split file | `doc.set_toc()` with chapter substructure |
| **XMP metadata** | Read/write XMP metadata for better cataloging | PyMuPDF XMP support or `python-xmp-toolkit` |
| **Page label preservation** | Maintain page numbering schemes (roman numerals, etc.) | PyMuPDF page labels API |
| **Custom metadata injection** | Add custom metadata (tags, categories) to split files | `doc.set_metadata()` with custom fields |

### 1.5 Output & Quality

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **PDF/A compliance** | Output PDF/A compliant files for archival purposes | PyMuPDF PDF/A output options or `pikepdf` |
| **Compression optimization** | Compress images and streams in output PDFs | `doc.save(deflate=True, garbage=4, clean=True)` |
| **PDF linearization** | Optimize for fast web viewing (linearized/"fast web view") | `doc.save(linear=True)` |
| **Image downsampling** | Reduce image resolution for smaller output files | PyMuPDF image extraction + Pillow resize + reinsertion |
| **Grayscale conversion** | Convert color pages to grayscale for smaller files | `page.get_pixmap(colorspace=fitz.csGRAY)` |
| **Page rotation** | Auto-detect and fix rotated pages | `page.rotation` detection + correction |
| **Crop box adjustment** | Remove whitespace/margins from pages | `page.set_cropbox()` with content detection |
| **Watermark removal/addition** | Add or remove watermarks during splitting | PyMuPDF overlay/underlay operations |

### 1.6 Multi-Language Chapter Detection

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **i18n chapter patterns** | Detect chapters in Spanish (Capítulo), French (Chapitre), German (Kapitel), etc. | Extend `CHAPTER_PATTERNS` with localized regexes |
| **CJK heading detection** | Detect chapter headings in Chinese/Japanese/Korean | Unicode-aware regex + CJK font size analysis |
| **RTL language support** | Handle Arabic/Hebrew right-to-left documents | PyMuPDF text direction detection |
| **Auto language detection** | Automatically detect document language for pattern selection | `langdetect` or `lingua-py` library |

### 1.7 Analysis & Reporting

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Split statistics report** | Generate detailed report (page counts, sizes, confidence scores) | Rich tables + optional JSON/CSV export |
| **Chapter overlap detection** | Warn about overlapping or missing page ranges | Validation in `DetectionResult` |
| **Visual page map** | Show a visual representation of chapter boundaries | Rich panel with colored page blocks |
| **Content analysis** | Word count, image count, table count per chapter | PyMuPDF content extraction + analysis |
| **PDF structure analysis** | Report on PDF internal structure (fonts, images, forms) | `doc.get_page_fonts()`, `doc.get_page_images()` |

---

## 2. EPUB Splitter Enhancements

### 2.1 Advanced Detection & Splitting

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Footnote/endnote handling** | Keep footnotes with their referencing chapter | Parse `<aside epub:type="footnote">` and `<a>` references |
| **Cross-reference preservation** | Fix internal links between split EPUB files | Remap `href` attributes across content files |
| **Reading order analysis** | Detect and respect non-linear reading order | Parse EPUB spine `linear` attribute |
| **Multi-level splitting** | Split at parts, then chapters, then sections hierarchically | Recursive TOC traversal with depth parameter |
| **Smart content boundary detection** | Split within a single HTML file at heading boundaries | DOM tree splitting at heading elements |
| **Cover page handling** | Detect and optionally include/exclude cover page | Parse `<meta name="cover">` and cover guide references |
| **Front/back matter detection** | Identify and separately handle preface, index, appendix | EPUB landmark navigation + semantic detection |

### 2.2 EPUB Validation & Standards

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **EPUB validation** | Validate output EPUBs against EPUB specification | `epubcheck` (Java tool) or custom EPUB 3.x validator |
| **EPUB 2 ↔ 3 detection** | Auto-detect EPUB version and handle differences | Check `content.opf` version attribute |
| **Accessibility metadata** | Preserve and validate WCAG/EPUB accessibility metadata | Parse `<meta property="schema:accessMode">` |
| **EPUB 3 fixed-layout support** | Handle fixed-layout EPUBs (vs reflowable) | Detect `rendition:layout` property |
| **Media overlay support** | Handle EPUB 3 media overlays (synchronized audio) | Parse SMIL files and media-overlay attributes |

### 2.3 Content Processing

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Image optimization** | Compress images in split EPUBs to reduce file size | Pillow-based optimization of embedded images |
| **CSS deduplication** | Remove unused CSS rules in split chapters | Parse CSS + DOM to identify used selectors |
| **Font subsetting** | Subset fonts to include only characters used per chapter | `fonttools` library for font subsetting |
| **Language detection** | Auto-detect EPUB language for localized chapter patterns | `langdetect` on extracted text content |
| **DRM detection** | Detect and warn about DRM-protected EPUBs (cannot split) | Check for Adobe DRM / Apple FairPlay encryption |
| **Inline image handling** | Properly handle base64-encoded inline images | Parse `data:` URIs in `<img>` tags |

### 2.4 Output Options

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **EPUB → PDF per chapter** | Output individual chapters as PDF files | WeasyPrint or PyMuPDF HTML → PDF rendering |
| **EPUB → HTML export** | Export chapters as standalone HTML files | Extract + fix resource references |
| **EPUB → Markdown export** | Convert chapters to Markdown format | `html2text` or `markdownify` library |
| **EPUB → plain text** | Extract plain text per chapter | lxml text extraction |
| **Custom CSS injection** | Apply custom styling to output EPUBs | Inject user CSS into `<head>` of content files |
| **Reading statistics** | Word count, estimated reading time per chapter | Text extraction + word counting |

---

## 3. Video Splitter (New Module)

### 3.1 Core Splitting Capabilities

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Scene detection splitting** | Detect and split at scene changes (cuts, fades, dissolves) | `scenedetect` (PySceneDetect) - ContentDetector, ThresholdDetector |
| **Chapter-based splitting** | Split using embedded chapter markers (MKV, MP4) | `ffprobe` to read chapter metadata + `ffmpeg` for splitting |
| **Timestamp-based splitting** | Split at user-specified timestamps | `ffmpeg -ss START -to END` |
| **Duration-based splitting** | Split into equal-duration segments | Calculate total duration / N segments |
| **File size-based splitting** | Split so each segment is under a target size | Estimate bitrate → calculate duration per segment |
| **Silence-based splitting** | Detect audio silence and split at silent gaps | `ffmpeg silencedetect` filter or `pydub.silence` |
| **Subtitle-based splitting** | Split at subtitle/caption boundaries (chapters, scenes) | Parse SRT/VTT/ASS files for chapter markers |
| **Keyframe-aware splitting** | Split only at keyframes (I-frames) for clean cuts | `ffmpeg -c copy` with keyframe alignment |
| **Black frame detection** | Split at black frames (common in TV recordings) | `ffmpeg blackdetect` filter |
| **Logo/watermark change detection** | Detect channel logo changes for splitting recordings | Frame comparison with ROI masking |

### 3.2 Format & Encoding

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Lossless splitting** | Split without re-encoding (stream copy) | `ffmpeg -c copy` for instant splitting |
| **Re-encoding options** | Transcode while splitting (change codec, resolution, etc.) | FFmpeg encoding profiles (H.264, H.265, VP9, AV1) |
| **Quality presets** | Pre-configured quality settings (low/medium/high/lossless) | CRF-based encoding with predefined values |
| **Resolution scaling** | Resize video during splitting | `ffmpeg -vf scale=WIDTH:HEIGHT` |
| **Container format conversion** | Convert between MP4, MKV, WebM, AVI, MOV | FFmpeg container remuxing |
| **Audio track selection** | Choose which audio tracks to include in split files | `ffmpeg -map 0:a:N` for track selection |
| **Subtitle embedding** | Embed or extract subtitles during splitting | `ffmpeg -c:s copy` or subtitle burn-in |
| **HDR handling** | Preserve HDR metadata (HDR10, Dolby Vision) | FFmpeg HDR passthrough and tone mapping |

### 3.3 Analysis & Preview

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Thumbnail generation** | Generate thumbnail images for each detected segment | `ffmpeg -vf thumbnail` or PySceneDetect frame saving |
| **Scene change visualization** | Visual timeline of detected scene changes | Matplotlib/Rich timeline chart |
| **Video metadata report** | Report codec, resolution, duration, bitrate, chapters | `ffprobe -show_format -show_streams` JSON output |
| **Preview mode** | Show detected split points without actually splitting | PySceneDetect scene listing |
| **Waveform visualization** | Show audio waveform to help identify split points | `ffmpeg showwavespic` filter |

### 3.4 Dependencies & Installation

```
ffmpeg (system dependency - required)
scenedetect (pip - optional for scene detection)
ffmpeg-python (pip - Python FFmpeg bindings)
```

---

## 4. Audio Splitter (New Module)

### 4.1 Core Splitting Capabilities

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Silence-based splitting** | Detect silence gaps and split between audio segments | `pydub.silence.detect_silence()` or `librosa` energy analysis |
| **Chapter marker splitting** | Split using embedded chapter markers (M4B audiobooks, MP3 chapters) | `mutagen` for reading chapter metadata |
| **CUE sheet splitting** | Split audio files based on CUE sheet track definitions | Custom CUE parser + `pydub` slicing |
| **Timestamp-based splitting** | Split at user-specified timestamps | `pydub` slice operations |
| **Duration-based splitting** | Split into equal-duration segments | Total duration / N calculation |
| **File size-based splitting** | Split so each segment is under a target size | Estimate based on bitrate |
| **BPM-based splitting** | Split music at beat/bar boundaries | `librosa.beat.beat_track()` for beat detection |
| **Voice activity detection** | Split based on speech vs non-speech segments | `webrtcvad` or `silero-vad` models |
| **Spoken chapter detection** | Detect chapter announcements in audiobooks via STT | `whisper` (OpenAI) or `vosk` for speech-to-text |
| **Intro/outro detection** | Detect and split at music intros/outros in podcasts | Audio fingerprinting + energy analysis |
| **Track-based splitting** | Split multi-track audio files (stems) | Channel/track separation |

### 4.2 Audio Processing

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Audio normalization** | Normalize volume levels across split segments | `pydub` normalization or `ffmpeg loudnorm` |
| **Fade in/out** | Apply crossfade effects at split points | `pydub` fade operations |
| **Noise reduction** | Remove background noise from segments | `noisereduce` library |
| **Format conversion** | Convert between MP3, FLAC, WAV, OGG, AAC, M4A, OPUS | `pydub.export()` with format parameter |
| **Sample rate conversion** | Change sample rate during splitting | `librosa.resample()` or `pydub` |
| **Channel conversion** | Convert mono ↔ stereo | `pydub` channel operations |
| **Bitrate selection** | Choose output bitrate for compressed formats | `pydub.export(bitrate="320k")` |

### 4.3 Metadata & Tags

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **ID3 tag preservation** | Preserve and update ID3 tags in split MP3 files | `mutagen` library |
| **Album art handling** | Preserve or extract cover art | `mutagen` album art fields |
| **Chapter metadata injection** | Add chapter markers to M4B/M4A output | `mutagen.mp4` chapter atoms |
| **Podcast RSS metadata** | Extract chapter info from podcast RSS feeds | `feedparser` + podcast namespace chapters |
| **Auto-tagging** | Auto-generate track numbers, titles for split files | Sequential numbering + detected titles |

### 4.4 Analysis & Preview

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Waveform visualization** | Display audio waveform with split points marked | `librosa.display.waveshow()` or Rich-based ASCII |
| **Spectrogram analysis** | Show frequency analysis for split points | `librosa.display.specshow()` |
| **Silence detection preview** | Show detected silence gaps before splitting | Report silence timestamps and durations |
| **Audio fingerprinting** | Identify and deduplicate audio segments | `chromaprint` / `acoustid` |
| **Duration report** | Show duration and size of each split segment | `pydub` length calculation |

### 4.5 Dependencies

```
pydub (pip - core audio manipulation)
librosa (pip - optional, for advanced audio analysis)
mutagen (pip - audio metadata/tags)
ffmpeg (system - audio codec support)
whisper/vosk (pip - optional, for speech-to-text chapter detection)
```

---

## 5. Document Splitter (New Module)

### 5.1 Word Document Splitting (DOCX)

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Split by headings** | Split at Heading 1, Heading 2, or custom heading styles | `python-docx` style name detection |
| **Split by sections** | Split at Word section breaks | `python-docx` section iteration |
| **Split by page breaks** | Split at explicit page breaks | Detect `<w:br w:type="page"/>` elements |
| **Split by page count** | Split into N-page chunks | Page break insertion + counting |
| **Style preservation** | Maintain all formatting, styles, themes in split files | Deep copy of document styles and themes |
| **Image handling** | Preserve embedded images in correct split file | Image relationship mapping |
| **Table splitting** | Handle tables that span across split points | Table detection and boundary respect |
| **Header/footer preservation** | Maintain headers and footers in split files | Section-based header/footer copying |
| **Comment preservation** | Keep comments/track changes in relevant split files | Comment anchor mapping |
| **TOC regeneration** | Generate new TOC for each split file | `python-docx` TOC field handling |

### 5.2 PowerPoint Splitting (PPTX)

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Split by sections** | Split at PowerPoint section boundaries | `python-pptx` section detection |
| **Split by slide count** | Split into chunks of N slides | Slide iteration with `python-pptx` |
| **Split by slide range** | Extract specific slides (e.g., 1-5, 10-15) | `python-pptx` slide copying |
| **Per-slide export** | Export each slide as a separate file | Individual PPTX creation |
| **Slide master preservation** | Maintain slide masters and layouts | Copy slide layouts and masters |
| **Speaker notes handling** | Preserve speaker notes in split files | `slide.notes_slide` copying |
| **Animation preservation** | Maintain slide animations and transitions | XML-level preservation |
| **Embedded media handling** | Handle embedded audio/video in slides | Media relationship mapping |
| **Slide → image export** | Export slides as PNG/JPEG images | `python-pptx` + Pillow or LibreOffice headless |

### 5.3 Excel Splitting (XLSX)

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Split by worksheet** | Export each worksheet as a separate file | `openpyxl` worksheet iteration |
| **Split by row count** | Split large sheets into chunks of N rows | Row slicing with `openpyxl` |
| **Split by column** | Split based on a grouping column value | Group-by logic on column values |
| **Preserve formatting** | Maintain cell formatting, conditional formatting | `openpyxl` style copying |
| **Formula handling** | Handle formulas that reference across sheets | Formula dependency analysis |
| **Chart handling** | Keep charts in the correct split file | Chart sheet association |
| **Pivot table handling** | Preserve pivot tables during splitting | Pivot table data range mapping |

### 5.4 Markdown Splitting

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Split by headings** | Split at `#`, `##`, or configurable heading level | Regex-based heading detection |
| **Split by horizontal rules** | Split at `---`/`***` dividers | Pattern matching |
| **Front matter preservation** | Handle YAML front matter in split files | `python-frontmatter` library |
| **Link reference fixing** | Fix relative links and image references | Path rewriting for split files |
| **Code block preservation** | Ensure code blocks aren't broken by splitting | State machine for fenced code blocks |

### 5.5 Other Document Formats

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **LaTeX splitting** | Split `.tex` files by `\chapter{}`, `\section{}` | Regex parsing of LaTeX commands |
| **HTML splitting** | Split HTML files by heading tags or `<section>` | `BeautifulSoup` / `lxml` DOM parsing |
| **CSV/TSV splitting** | Split large CSV files by row count or column value | `csv` module or `pandas` chunked reading |
| **JSON splitting** | Split large JSON arrays into smaller files | `ijson` for streaming JSON parsing |
| **XML splitting** | Split XML files by element boundaries | `lxml` iterparse for memory-efficient processing |
| **RTF splitting** | Split Rich Text Format files | `striprtf` or `pyrtf-ng` |
| **ODT splitting** | Split LibreOffice Writer documents | `odfpy` library |

### 5.6 Dependencies

```
python-docx (pip - Word document handling)
python-pptx (pip - PowerPoint handling)
openpyxl (pip - Excel handling)
python-frontmatter (pip - Markdown front matter)
odfpy (pip - optional, LibreOffice formats)
pandas (pip - optional, CSV/data splitting)
```

---

## 6. Image Splitter (New Module)

### 6.1 Multi-Page Image Splitting

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Multi-page TIFF splitting** | Split multi-page TIFF files into individual images | Pillow `ImageSequence.Iterator()` |
| **PDF to image extraction** | Extract each PDF page as an image | PyMuPDF `page.get_pixmap()` |
| **DICOM splitting** | Split multi-frame medical images | `pydicom` library |
| **Animated GIF frame extraction** | Extract individual frames from animated GIFs | Pillow frame iteration |
| **APNG frame extraction** | Extract frames from animated PNG files | Pillow APNG support |
| **WebP animation splitting** | Extract frames from animated WebP | Pillow WebP support |
| **ICO/ICNS splitting** | Extract different sizes from icon files | Pillow icon handling |

### 6.2 Spatial Image Splitting

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Grid splitting** | Split image into NxM grid cells | Pillow `Image.crop()` with calculated coordinates |
| **Sprite sheet splitting** | Extract individual sprites from sprite sheets | Grid detection + content-aware cropping |
| **Contact sheet splitting** | Split scanned contact sheets into individual photos | Edge detection + auto-crop |
| **Panorama segmentation** | Split panoramic images into overlapping sections | Configurable overlap percentage |
| **Custom region extraction** | Extract user-defined rectangular regions | Coordinate-based cropping |
| **Auto-crop splitting** | Detect and extract individual items from scanned pages | OpenCV contour detection |
| **Tile generation** | Generate map-style tiles at multiple zoom levels | Pillow resize + crop at power-of-2 scales |

### 6.3 Image Processing

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Format conversion** | Convert between PNG, JPEG, TIFF, WebP, BMP, etc. | Pillow `Image.save(format=...)` |
| **DPI handling** | Preserve or change DPI during splitting | Pillow DPI metadata |
| **Color space conversion** | Convert between RGB, CMYK, grayscale, etc. | Pillow `Image.convert()` |
| **Compression control** | Set output quality/compression level | Pillow quality parameter |
| **EXIF preservation** | Preserve EXIF metadata in split images | `piexif` or Pillow EXIF handling |
| **ICC profile handling** | Preserve color profiles | Pillow ICC profile support |
| **Thumbnail generation** | Generate thumbnails alongside full-size splits | Pillow `Image.thumbnail()` |
| **Batch resize** | Resize all split images to a target resolution | Pillow resize with aspect ratio |
| **Watermark addition** | Add watermark to split images | Pillow overlay/composite operations |

### 6.4 Analysis

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Image content detection** | Detect boundaries between images on a scanned page | OpenCV edge/contour detection |
| **Blank page detection** | Identify and skip blank/empty pages in TIFF stacks | Pixel value analysis (mean/std deviation) |
| **Duplicate detection** | Identify duplicate frames/images | Perceptual hashing (`imagehash` library) |
| **OCR integration** | Apply OCR to extracted images | Tesseract/EasyOCR integration |

### 6.5 Dependencies

```
Pillow (pip - core image manipulation)
opencv-python (pip - optional, advanced image analysis)
piexif (pip - optional, EXIF metadata)
imagehash (pip - optional, duplicate detection)
pydicom (pip - optional, medical image support)
```

---

## 7. AI/ML-Powered Features

### 7.1 Document Understanding

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **LLM-based chapter detection** | Use large language models to identify chapter boundaries from text | OpenAI API, Anthropic API, or local models (Ollama, llama.cpp) |
| **Topic modeling segmentation** | Cluster document sections by topic for intelligent splitting | `BERTopic`, `gensim` LDA, or `scikit-learn` NMF |
| **Semantic text segmentation** | Split based on semantic meaning changes | `sentence-transformers` + cosine similarity windowing |
| **Document layout analysis** | Detect headings, paragraphs, tables, figures from visual layout | `LayoutLMv3`, `Detectron2`, or `doctr` (docTR) |
| **Named entity-based splitting** | Split legal/business documents by entity sections | `spaCy` NER pipeline |
| **Summarization per chapter** | Auto-generate summaries for each split section | LLM APIs or `transformers` summarization models |
| **Auto-title generation** | Generate descriptive titles for untitled chapters | LLM-based title generation from content |

### 7.2 OCR & Vision

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Deep learning OCR** | Modern neural OCR for scanned documents | `EasyOCR`, `PaddleOCR`, `docTR` |
| **Handwriting recognition** | Detect handwritten text in scanned documents | `EasyOCR` handwriting mode, Google Vision API |
| **Table extraction** | Extract and preserve tables from PDFs | `camelot-py`, `tabula-py`, or `img2table` |
| **Figure/chart detection** | Detect and extract figures and charts | `Detectron2` or YOLO-based object detection |
| **Mathematical formula detection** | Detect and preserve LaTeX/math regions | Specialized math OCR models |
| **Document type classification** | Auto-classify document type (book, report, paper, slides) | Text/layout feature classification |

### 7.3 Audio/Video AI

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Speech-to-text chapter detection** | Transcribe audio and detect chapter transitions | `whisper` (OpenAI) or `faster-whisper` |
| **Speaker diarization splitting** | Split by speaker changes (interviews, meetings) | `pyannote.audio` speaker diarization |
| **Music/speech separation** | Separate music from speech in podcasts | `demucs` or `spleeter` source separation |
| **Emotion-based segmentation** | Split by emotional tone changes | `transformers` emotion classification |
| **Topic-based video segmentation** | Split videos by topic changes in narration | Transcript + topic modeling pipeline |
| **Face detection scene splitting** | Split video scenes by face/person changes | `face_recognition` or `mediapipe` |

### 7.4 Smart Configuration

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Auto-sensitivity tuning** | Automatically find optimal detection sensitivity | Grid search over sensitivity + cross-validation |
| **Learning from corrections** | Learn from user edits to improve future detection | Simple feedback loop with stored preferences |
| **Confidence calibration** | Calibrate confidence scores based on document type | Statistical calibration on known documents |
| **Strategy auto-selection** | Automatically choose the best detection strategy | Feature-based classifier on document properties |

### 7.5 Dependencies (Optional)

```
# Core ML
scikit-learn (pip - topic modeling, classification)
sentence-transformers (pip - semantic segmentation)
transformers (pip - various NLP tasks)
spacy (pip - NER, text processing)

# OCR
easyocr (pip - neural OCR)
paddleocr (pip - alternative OCR)
pytesseract (pip - Tesseract wrapper)

# Document Analysis
doctr (pip - document text recognition)
camelot-py (pip - table extraction)

# Audio/Video AI
whisper / faster-whisper (pip - speech-to-text)
pyannote.audio (pip - speaker diarization)

# LLM Integration
openai (pip - GPT API)
anthropic (pip - Claude API)
ollama (system - local LLM inference)
```

---

## 8. Unified CLI & TUI

### 8.1 Unified Command Interface

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Unified `lazy-splitter` command** | Single entry point: `lazy-splitter <file>` with auto-detection | Click group with `lazy-splitter split`, `lazy-splitter merge`, etc. |
| **File type auto-detection** | Automatically detect file type and route to appropriate splitter | `python-magic` or file extension mapping |
| **Subcommand structure** | `lazy-splitter pdf split`, `lazy-splitter video split`, etc. | Click multi-level command groups |
| **Global options** | Common options across all splitters (`--output-dir`, `--verbose`, `--dry-run`) | Click `@click.pass_context` with shared options |
| **Shell completions** | Tab completion for Bash, Zsh, Fish shells | `click` shell completion or `argcomplete` |
| **Man page generation** | Auto-generate man pages from CLI definitions | `click-man` library |
| **Command aliases** | Short aliases (e.g., `ls split` for `lazy-splitter split`) | Click command aliasing |

### 8.2 Interactive TUI

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Interactive file browser** | Browse and select files to split | `textual` FileOpen dialog |
| **Chapter preview TUI** | Interactive table of detected chapters with edit capability | `textual` DataTable widget |
| **Split point editor** | Visually adjust split points before splitting | `textual` custom widget with markers |
| **Progress dashboard** | Real-time progress with multiple file tracking | `textual` or `rich.live` dashboard |
| **Settings editor** | Interactive settings/configuration editor | `textual` form widgets |
| **Drag-and-drop support** | Accept files via drag-and-drop in terminal (iTerm2, etc.) | Terminal escape sequence detection |
| **Keyboard shortcuts** | Vim-like navigation in TUI mode | `textual` key bindings |

### 8.3 Configuration

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Config file support** | TOML/YAML configuration file (`~/.lazy-splitter.toml` or per-project) | `tomli`/`tomllib` (Python 3.11+) or `pyyaml` |
| **Profile support** | Named configuration profiles (e.g., `--profile audiobook`) | Config file sections |
| **Environment variables** | Configure via env vars (`LAZY_SPLITTER_OUTPUT_DIR`, etc.) | Click `envvar` parameter |
| **Per-file-type defaults** | Different default settings per file type | Config file sections by file type |
| **Config generation** | `lazy-splitter config init` to generate default config | Template-based config generation |
| **Config validation** | Validate config file and report errors | `pydantic` or `attrs` validation |

### 8.4 Output & Logging

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Verbose/debug mode** | Detailed logging for troubleshooting | `logging` module + `--verbose`/`--debug` flags |
| **Quiet mode** | Suppress all output except errors | `--quiet` flag |
| **JSON output** | Machine-readable output for scripting | `--json` flag with structured output |
| **Log file** | Write logs to file for later review | `logging.FileHandler` |
| **Dry-run mode** | Preview what would happen without making changes | `--dry-run` flag showing planned operations |
| **Color theme selection** | Choose between color themes (dark, light, no-color) | Rich theme support + `--no-color` flag |

---

## 9. Merge/Join - Reverse Operations

### 9.1 PDF Merging

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Basic PDF merge** | Combine multiple PDFs into one | PyMuPDF `doc.insert_pdf()` |
| **Page interleaving** | Interleave pages from two PDFs (e.g., front+back scanner) | Alternating page insertion |
| **TOC generation** | Generate TOC from merged file names | `doc.set_toc()` with source file entries |
| **Bookmark merging** | Combine bookmarks from all source PDFs | TOC concatenation with offset adjustment |
| **Page number renumbering** | Add continuous page numbering to merged PDF | Page label insertion |
| **Selective merge** | Choose specific pages from each source PDF | Page range specification per file |
| **Overlay/underlay** | Overlay letterhead/watermark on all pages | PyMuPDF page overlay operations |

### 9.2 EPUB Merging

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **EPUB merge** | Combine multiple EPUBs into a single EPUB | `ebooklib` content aggregation |
| **TOC generation** | Generate unified table of contents | Combined navigation document |
| **Metadata merging** | Intelligently merge metadata from sources | Configurable metadata priority |
| **Resource deduplication** | Remove duplicate images/CSS across merged EPUBs | Hash-based deduplication |

### 9.3 Video/Audio Concatenation

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Video concatenation** | Join multiple video files sequentially | FFmpeg concat demuxer or protocol |
| **Audio concatenation** | Join multiple audio files | `pydub` concatenation or FFmpeg |
| **Crossfade transitions** | Apply crossfade between joined segments | FFmpeg `xfade` filter |
| **Chapter marker generation** | Add chapter markers at join points | FFmpeg metadata chapter insertion |
| **Audio normalization on merge** | Normalize volume across all segments | `ffmpeg loudnorm` filter |

### 9.4 Document Merging

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **DOCX merge** | Combine multiple Word documents | `python-docx` section-based merging |
| **PPTX merge** | Combine multiple presentations | `python-pptx` slide copying |
| **Markdown merge** | Combine Markdown files with heading hierarchy | Concatenation with heading level adjustment |
| **CSV merge** | Concatenate CSV files (header handling) | `pandas` or `csv` module |

---

## 10. Batch Processing & Automation

### 10.1 Batch Operations

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Directory processing** | Process all files in a directory | `pathlib.Path.glob()` with type filtering |
| **Recursive scanning** | Recursively process files in subdirectories | `pathlib.Path.rglob()` |
| **Glob pattern support** | Process files matching patterns (e.g., `*.pdf`, `books/**/*.epub`) | Python `glob` module |
| **File filtering** | Filter by size, date, name pattern | `os.stat()` based filtering |
| **Parallel processing** | Process multiple files concurrently | `concurrent.futures.ProcessPoolExecutor` |
| **Async processing** | Non-blocking I/O for batch operations | `asyncio` + `aiofiles` |
| **Job queue** | Queue-based processing for large batches | `queue.Queue` or Redis-backed `rq` |
| **Resume interrupted jobs** | Resume batch processing after interruption | Progress checkpoint files (JSON/SQLite) |
| **Rate limiting** | Limit resource usage during batch processing | Configurable concurrency limits |

### 10.2 Workflow & Automation

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Directory watching** | Watch a directory for new files and auto-process | `watchdog` library |
| **Pipeline definitions** | Define multi-step processing pipelines (detect → split → convert → compress) | YAML/TOML pipeline config |
| **Post-processing hooks** | Run custom scripts/commands after splitting | Shell command execution hooks |
| **Email notifications** | Send email notifications on batch completion | `smtplib` or webhook integration |
| **Scheduling** | Schedule periodic batch processing | `schedule` library or system cron integration |
| **Input/output mapping** | Map input files to custom output directory structures | Template-based path generation |
| **Manifest files** | Generate manifest/index files for processed batches | JSON/CSV manifest generation |

### 10.3 Reporting

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Processing reports** | Generate detailed reports of batch operations | Rich tables + JSON/HTML/CSV export |
| **Error aggregation** | Collect and summarize all errors from batch processing | Error log with file associations |
| **Statistics dashboard** | Show processing statistics (files processed, total size, time) | Rich panel with summary stats |
| **Audit logging** | Detailed log of all operations performed | Structured logging to file |

---

## 11. Format Conversion

### 11.1 Document Conversions

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **PDF → EPUB** | Convert PDF to reflowable EPUB | PyMuPDF text extraction → EPUB construction |
| **EPUB → PDF** | Convert EPUB to PDF | WeasyPrint, `prince`, or PyMuPDF HTML rendering |
| **PDF → images** | Extract PDF pages as PNG/JPEG/TIFF | PyMuPDF `page.get_pixmap()` |
| **Images → PDF** | Combine images into a single PDF | PyMuPDF or Pillow + `img2pdf` |
| **PDF → HTML** | Convert PDF to HTML | PyMuPDF text extraction with structure |
| **HTML → PDF** | Convert HTML to PDF | `weasyprint` or `playwright` |
| **Markdown → PDF** | Convert Markdown to PDF | `markdown` → HTML → WeasyPrint PDF |
| **Markdown → EPUB** | Convert Markdown to EPUB | `markdown` → `ebooklib` EPUB construction |
| **DOCX → PDF** | Convert Word documents to PDF | LibreOffice headless or `docx2pdf` |
| **PPTX → PDF** | Convert presentations to PDF | LibreOffice headless |
| **EPUB → MOBI** | Convert EPUB to Kindle format | `kindlegen` or Calibre's `ebook-convert` |
| **EPUB → AZW3** | Convert EPUB to Kindle AZW3 format | Calibre's `ebook-convert` |

### 11.2 Media Conversions

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Video format conversion** | MP4 ↔ MKV ↔ WebM ↔ AVI | FFmpeg container remuxing or re-encoding |
| **Audio format conversion** | MP3 ↔ FLAC ↔ WAV ↔ OGG ↔ AAC | `pydub` or FFmpeg |
| **Image format conversion** | PNG ↔ JPEG ↔ WebP ↔ TIFF ↔ BMP | Pillow `Image.save()` |
| **Video → Audio extraction** | Extract audio track from video files | `ffmpeg -vn` |
| **Video → GIF** | Convert video clips to animated GIFs | FFmpeg + Pillow palette optimization |
| **Audio → waveform image** | Generate waveform visualization | `librosa` + `matplotlib` |

### 11.3 Dependencies

```
weasyprint (pip - HTML/CSS to PDF)
img2pdf (pip - images to PDF)
docx2pdf (pip - Word to PDF, requires LibreOffice)
markdown (pip - Markdown processing)
libreoffice (system - optional, document conversion)
```

---

## 12. Cloud & Web Integration

### 12.1 REST API

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **FastAPI REST server** | HTTP API for all splitting operations | `fastapi` + `uvicorn` |
| **File upload endpoint** | Upload files for splitting via multipart form | FastAPI `UploadFile` |
| **Async processing** | Background task processing for large files | FastAPI `BackgroundTasks` or Celery |
| **WebSocket progress** | Real-time progress updates via WebSocket | FastAPI WebSocket support |
| **API key authentication** | Secure API access with API keys | FastAPI dependency injection |
| **Rate limiting** | API rate limiting for multi-tenant use | `slowapi` or custom middleware |
| **OpenAPI documentation** | Auto-generated API documentation | FastAPI built-in Swagger/ReDoc |
| **Webhook callbacks** | Notify external systems on completion | HTTP POST to callback URLs |

### 12.2 Web UI

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Streamlit web app** | Simple web interface for splitting | `streamlit` with file upload |
| **Gradio interface** | ML-friendly web UI with preview | `gradio` interface components |
| **React/Vue frontend** | Full-featured web application | SPA with API backend |
| **File preview** | Preview PDF/EPUB/images in browser | PDF.js, EPUB.js rendering |
| **Drag-and-drop upload** | Browser drag-and-drop file upload | HTML5 drag-and-drop API |
| **Download as ZIP** | Package split files as ZIP for download | `zipfile` module |
| **Progress visualization** | Real-time progress bars in browser | WebSocket + progress UI |

### 12.3 Cloud Storage Integration

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **AWS S3** | Read from and write to S3 buckets | `boto3` |
| **Google Cloud Storage** | Read from and write to GCS buckets | `google-cloud-storage` |
| **Azure Blob Storage** | Read from and write to Azure containers | `azure-storage-blob` |
| **Dropbox integration** | Read from and write to Dropbox | `dropbox` SDK |
| **Google Drive** | Read from and write to Google Drive | `google-api-python-client` |
| **OneDrive/SharePoint** | Read from and write to Microsoft cloud | Microsoft Graph API |
| **FTP/SFTP** | Read from and write to FTP servers | `paramiko` / `ftplib` |
| **URL input** | Download files from URLs for processing | `httpx` or `requests` |

### 12.4 Deployment

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Docker image** | Containerized deployment | Multi-stage Dockerfile with FFmpeg |
| **Docker Compose** | Multi-service deployment (API + worker + storage) | Docker Compose YAML |
| **Kubernetes Helm chart** | Kubernetes deployment | Helm chart with scaling |
| **AWS Lambda** | Serverless splitting for small files | Lambda + S3 triggers |
| **Google Cloud Functions** | Serverless on GCP | Cloud Functions + GCS triggers |
| **Fly.io / Railway** | Easy platform deployment | Dockerfile-based deployment |

---

## 13. Developer Experience & API

### 13.1 Python API Improvements

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Fluent/builder API** | Chainable API: `Splitter(file).strategy("hybrid").sensitivity("high").split()` | Builder pattern implementation |
| **Context manager support** | `with PDFSplitter("file.pdf") as splitter:` | `__enter__`/`__exit__` methods |
| **Iterator/generator support** | Yield chapters one at a time for memory efficiency | Generator-based splitting |
| **Async API** | `await splitter.split_async(file)` | `asyncio` with async file I/O |
| **Callback hooks** | `splitter.on_chapter_detected(callback)` | Event emitter pattern |
| **Type stubs** | Complete type annotations and `py.typed` marker | `mypy` strict mode compliance |
| **Dataclass-based config** | Typed configuration objects instead of keyword args | `pydantic` or `dataclasses` based config |
| **Result objects** | Rich result objects with success/failure/warnings | `SplitResult` dataclass with details |

### 13.2 Plugin & Extension System

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Plugin architecture** | Allow third-party plugins for new file types, strategies | `pluggy` or `stevedore` entry-point plugins |
| **Custom strategy registration** | Register custom detection strategies at runtime | Strategy registry with decorator: `@register_strategy("my_custom")` |
| **Custom file type handlers** | Add support for new file types via plugins | Abstract base class + plugin discovery |
| **Pre/post processing hooks** | Hooks that run before/after splitting operations | Event hook system |
| **Output format plugins** | Custom output format handlers | Output writer interface |
| **Detection pipeline** | Composable detection pipeline with middleware | Pipeline pattern with filter chain |

### 13.3 Integration & Tooling

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Jupyter notebook integration** | Rich display of results in Jupyter | `_repr_html_()` methods on result objects |
| **IPython magic commands** | `%split file.pdf` in IPython/Jupyter | IPython extension registration |
| **Pandas integration** | Return chapter data as DataFrame | `to_dataframe()` method on results |
| **Pre-commit hook** | Split large files before committing | `pre-commit` hook configuration |
| **GitHub Action** | GitHub Action for splitting files in CI/CD | GitHub Action YAML definition |
| **VS Code extension** | Split files directly from VS Code | VS Code extension API |

### 13.4 Testing & Quality

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Property-based testing** | Generate random PDFs/EPUBs for testing | `hypothesis` library |
| **Benchmark suite** | Performance benchmarks for large files | `pytest-benchmark` |
| **Mutation testing** | Verify test quality with mutation testing | `mutmut` |
| **Integration test fixtures** | Real-world PDF/EPUB test files | Test fixture downloads or generation |
| **Coverage enforcement** | Minimum coverage thresholds | `pytest-cov` with `--cov-fail-under` |
| **Fuzz testing** | Test with malformed/corrupted input files | `python-afl` or custom fuzzers |

---

## 14. Cross-cutting Platform Features

### 14.1 Internationalization & Localization

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **CLI message translation** | Translate CLI output to multiple languages | `gettext` / `babel` |
| **Multi-language chapter patterns** | Built-in chapter patterns for 20+ languages | Localized regex pattern sets |
| **Unicode filename handling** | Properly handle Unicode in output filenames | `unicodedata.normalize()` + safe encoding |
| **RTL output support** | Proper display of RTL languages in CLI | Rich BiDi support |

### 14.2 Performance & Scalability

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Memory-efficient processing** | Stream-based processing for large files | Generator/iterator patterns, memory-mapped files |
| **Large file support** | Handle files > 1GB efficiently | Chunked processing, temp file management |
| **Multiprocessing** | Parallel page/chapter processing | `multiprocessing.Pool` or `concurrent.futures` |
| **Caching** | Cache detection results for re-splitting | `diskcache` or `shelve` |
| **Lazy loading** | Only load file content when needed | Lazy attribute access patterns |
| **Progress persistence** | Resume interrupted operations | Checkpoint files with processed page tracking |
| **Memory profiling** | Track and report memory usage | `tracemalloc` integration |

### 14.3 Reliability & Safety

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Atomic file writes** | Write to temp files, then rename (prevents corruption) | `tempfile` + `os.rename()` |
| **Input validation** | Validate files before processing (corruption, DRM, etc.) | File header checks, magic number validation |
| **Checksum verification** | Generate checksums for output files | `hashlib` SHA-256 for each output file |
| **Rollback on error** | Clean up partial output if splitting fails | Context manager with cleanup |
| **Backup originals** | Optionally backup original files before processing | File copy before modification |
| **File locking** | Prevent concurrent access to same file | `filelock` library |
| **Temp file cleanup** | Ensure temporary files are cleaned up | `tempfile.TemporaryDirectory` with context manager |
| **Graceful interruption** | Handle Ctrl+C gracefully with cleanup | `signal` handler with cleanup |

### 14.4 User Experience

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **Update checker** | Notify users of new versions | `packaging` version comparison with PyPI API |
| **Usage analytics** | Optional anonymous usage statistics | Opt-in telemetry with `sentry-sdk` or custom |
| **Error reporting** | Structured error messages with suggestions | Custom exception hierarchy with help text |
| **Undo/history** | Track operations for undo capability | Operation log with reverse operations |
| **Shell integration** | Register as file handler in OS | Desktop entry files / Windows registry |
| **Notification system** | OS-level notifications on completion | `plyer` or `notify-py` |
| **Accessibility** | Screen reader friendly CLI output | Rich accessibility features |

### 14.5 Documentation & Community

| Feature | Description | Library/Approach |
|---------|-------------|-----------------|
| **API documentation** | Auto-generated API docs | `sphinx` + `sphinx-autodoc` |
| **Tutorial notebooks** | Jupyter notebooks with usage examples | Interactive examples in `examples/` |
| **Video tutorials** | Embedded video guides | YouTube/Loom links in docs |
| **Cookbook/recipes** | Common use-case recipes | Markdown cookbook documentation |
| **Community plugins directory** | Registry of community-contributed plugins | GitHub-based plugin listing |
| **Discord/Slack community** | Community chat for support | Discord server |

---

## Feature Count Summary

| Category | Feature Count |
|----------|:------------:|
| 1. PDF Splitter Enhancements | 38 |
| 2. EPUB Splitter Enhancements | 24 |
| 3. Video Splitter (New) | 24 |
| 4. Audio Splitter (New) | 27 |
| 5. Document Splitter (New) | 33 |
| 6. Image Splitter (New) | 22 |
| 7. AI/ML-Powered Features | 23 |
| 8. Unified CLI & TUI | 27 |
| 9. Merge/Join Operations | 18 |
| 10. Batch Processing | 18 |
| 11. Format Conversion | 18 |
| 12. Cloud & Web Integration | 26 |
| 13. Developer Experience | 26 |
| 14. Cross-cutting Features | 28 |
| **Total** | **352** |

---

## Recommended Priority Tiers

### Tier 1 - Core Value (Next Release)
- Unified `lazy-splitter` CLI command with auto-detection
- PDF: Split by page range, password support, OCR integration
- EPUB: Cross-reference preservation, validation, footnote handling
- Config file support (TOML)
- Dry-run mode, JSON output, verbose logging
- Merge/join for PDF and EPUB (reverse operations)

### Tier 2 - New Modules (v0.3-0.4)
- Video Splitter: scene detection, chapter splitting, silence splitting
- Audio Splitter: silence detection, chapter markers, CUE sheets
- Document Splitter: DOCX headings, PPTX sections, Markdown headings
- Image Splitter: TIFF splitting, grid splitting, PDF→images

### Tier 3 - Intelligence Layer (v0.5)
- AI/ML chapter detection (LLM integration, topic modeling)
- Deep learning OCR (EasyOCR, PaddleOCR)
- Auto-sensitivity tuning
- Content summarization

### Tier 4 - Platform Features (v0.6+)
- Interactive TUI (Textual)
- Batch processing with parallel execution
- Plugin/extension system
- REST API (FastAPI)
- Cloud storage integration
- Web UI (Streamlit/Gradio)
- Docker deployment

---

## Architecture Recommendations

### Modular Package Structure
```
src/
├── lazy_splitter/           # Unified package
│   ├── __init__.py
│   ├── cli.py               # Unified CLI entry point
│   ├── config.py            # Configuration management
│   ├── core/                # Shared core
│   │   ├── base.py          # Abstract base classes (BaseSplitter, BaseDetector)
│   │   ├── models.py        # Shared data models
│   │   ├── plugins.py       # Plugin system
│   │   └── utils.py         # Shared utilities
│   ├── pdf/                 # PDF module
│   ├── epub/                # EPUB module
│   ├── video/               # Video module
│   ├── audio/               # Audio module
│   ├── document/            # Document module (DOCX, PPTX, XLSX, MD)
│   ├── image/               # Image module
│   ├── merge/               # Merge/join operations
│   ├── convert/             # Format conversion
│   ├── batch/               # Batch processing
│   ├── ai/                  # AI/ML features
│   ├── api/                 # REST API
│   └── tui/                 # Terminal UI
```

### Optional Dependency Groups
```toml
[project.optional-dependencies]
video = ["scenedetect", "ffmpeg-python"]
audio = ["pydub", "mutagen", "librosa"]
document = ["python-docx", "python-pptx", "openpyxl"]
image = ["Pillow", "opencv-python"]
ai = ["sentence-transformers", "easyocr", "openai"]
ocr = ["pytesseract", "easyocr"]
web = ["fastapi", "uvicorn"]
cloud = ["boto3", "google-cloud-storage"]
tui = ["textual"]
all = ["lazy-splitter[video,audio,document,image,ai,web,cloud,tui]"]
```

---

*This feature catalog was generated through deep research into existing tools (PyPDF2/pypdf, Calibre, FFmpeg, PySceneDetect, pydub, python-docx, Pillow, and many more), competitive analysis, and domain expertise across document processing, multimedia handling, and developer tooling.*
