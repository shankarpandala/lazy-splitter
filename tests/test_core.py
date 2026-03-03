"""Tests for the lazy_splitter core module."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from lazy_splitter.core.models import (
    Chapter,
    EpubChapter,
    VideoSegment,
    AudioSegment,
    DocumentSection,
    ImageFrame,
    DetectionResult,
    SplitResult,
    MergeResult,
    ConversionResult,
)
from lazy_splitter.core.utils import (
    sanitize_filename,
    detect_file_type,
    format_duration,
    format_file_size,
    ensure_dir,
    validate_file,
)
from lazy_splitter.core.exceptions import (
    LazySplitterError,
    FileTypeError,
    DetectionError,
    SplitError,
    MergeError,
    ConversionError,
    ConfigError,
    PasswordRequiredError,
    DRMError,
    PluginError,
    CloudError,
)
from lazy_splitter.core.i18n import get_patterns, CHAPTER_PATTERNS
from lazy_splitter.core.config import LazyConfig


# === Model Tests ===


class TestChapter:
    def test_chapter_creation(self) -> None:
        ch = Chapter(title="Chapter 1", start_page=1, end_page=10)
        assert ch.title == "Chapter 1"
        assert ch.start_page == 1
        assert ch.end_page == 10
        assert ch.page_count == 10

    def test_chapter_str(self) -> None:
        ch = Chapter(title="Intro", start_page=1, end_page=5)
        assert "Intro" in str(ch)

    def test_chapter_confidence(self) -> None:
        ch = Chapter(title="Test", start_page=1, end_page=2, confidence=0.85)
        assert ch.confidence == 0.85


class TestVideoSegment:
    def test_video_segment_duration(self) -> None:
        seg = VideoSegment(title="Scene 1", start_time=0.0, end_time=30.5)
        assert seg.duration == pytest.approx(30.5)

    def test_video_segment_defaults(self) -> None:
        seg = VideoSegment(title="Scene", start_time=0.0, end_time=10.0)
        assert seg.detection_method == "unknown"
        assert seg.confidence == 1.0


class TestAudioSegment:
    def test_audio_segment_duration(self) -> None:
        seg = AudioSegment(title="Track 1", start_time=0.0, end_time=180.0)
        assert seg.duration == pytest.approx(180.0)


class TestDetectionResult:
    def test_detection_result(self) -> None:
        chapters = [
            Chapter(title="Ch 1", start_page=1, end_page=5),
            Chapter(title="Ch 2", start_page=6, end_page=10),
        ]
        result = DetectionResult(
            chapters=chapters,
            strategy_used="hybrid",
            total_items=10,
        )
        assert result.chapter_count == 2
        assert result.strategy_used == "hybrid"

    def test_detection_result_to_dict(self) -> None:
        result = DetectionResult(
            chapters=[Chapter(title="Ch 1", start_page=1, end_page=5)],
            strategy_used="bookmarks",
            total_items=5,
        )
        d = result.to_dict()
        assert d["strategy_used"] == "bookmarks"
        assert d["chapter_count"] == 1

    def test_detection_result_to_json(self) -> None:
        result = DetectionResult(
            chapters=[Chapter(title="Ch 1", start_page=1, end_page=5)],
            strategy_used="test",
            total_items=5,
        )
        j = result.to_json()
        parsed = json.loads(j)
        assert parsed["strategy_used"] == "test"


class TestSplitResult:
    def test_split_result_success(self) -> None:
        result = SplitResult(
            created_files=[Path("/tmp/a.pdf"), Path("/tmp/b.pdf")],
            source_path=Path("/tmp/src.pdf"),
        )
        assert result.success is True
        assert result.file_count == 2

    def test_split_result_with_errors(self) -> None:
        result = SplitResult(
            created_files=[],
            source_path=Path("/tmp/src.pdf"),
            errors=["Something failed"],
        )
        assert result.success is False


# === Utils Tests ===


class TestSanitizeFilename:
    def test_basic(self) -> None:
        assert sanitize_filename("Hello World") == "Hello_World"

    def test_invalid_chars(self) -> None:
        result = sanitize_filename('File: "test" <1>')
        assert ":" not in result
        assert '"' not in result
        assert "<" not in result

    def test_max_length(self) -> None:
        long_name = "A" * 200
        result = sanitize_filename(long_name, max_length=50)
        assert len(result) <= 50

    def test_empty(self) -> None:
        result = sanitize_filename("")
        assert result == "untitled"


class TestDetectFileType:
    def test_pdf(self) -> None:
        assert detect_file_type(Path("test.pdf")) == "pdf"

    def test_epub(self) -> None:
        assert detect_file_type(Path("test.epub")) == "epub"

    def test_mp4(self) -> None:
        assert detect_file_type(Path("test.mp4")) == "video"

    def test_mp3(self) -> None:
        assert detect_file_type(Path("test.mp3")) == "audio"

    def test_docx(self) -> None:
        assert detect_file_type(Path("test.docx")) == "docx"

    def test_png(self) -> None:
        assert detect_file_type(Path("test.png")) == "image"

    def test_unknown(self) -> None:
        with pytest.raises(FileTypeError):
            detect_file_type(Path("test.xyz"))


class TestFormatDuration:
    def test_seconds(self) -> None:
        result = format_duration(45)
        assert "45" in result

    def test_minutes(self) -> None:
        result = format_duration(125)
        assert "2" in result


class TestFormatFileSize:
    def test_bytes(self) -> None:
        result = format_file_size(500)
        assert "B" in result

    def test_megabytes(self) -> None:
        result = format_file_size(1024 * 1024 * 5)
        assert "MB" in result or "MiB" in result or "5" in result


class TestEnsureDir:
    def test_creates_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            new_dir = Path(tmp) / "sub" / "dir"
            result = ensure_dir(new_dir)
            assert result.is_dir()


class TestValidateFile:
    def test_nonexistent(self) -> None:
        with pytest.raises(FileNotFoundError):
            validate_file(Path("/nonexistent/file.txt"))

    def test_existing_file(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".txt") as f:
            assert validate_file(Path(f.name)) is True


# === I18n Tests ===


class TestI18n:
    def test_english_patterns(self) -> None:
        patterns = get_patterns("en")
        assert len(patterns) > 0

    def test_spanish_patterns(self) -> None:
        patterns = get_patterns("es")
        assert any("cap" in p.lower() for p in patterns)

    def test_supported_languages(self) -> None:
        assert "en" in CHAPTER_PATTERNS
        assert "fr" in CHAPTER_PATTERNS
        assert "de" in CHAPTER_PATTERNS
        assert "ja" in CHAPTER_PATTERNS
        assert len(CHAPTER_PATTERNS) >= 15


# === Config Tests ===


class TestConfig:
    def test_default_config(self) -> None:
        config = LazyConfig()
        assert config.sensitivity == "medium"
        assert config.strategy == "auto"
        assert config.verbose is False
        assert config.dry_run is False

    def test_config_to_dict(self) -> None:
        config = LazyConfig(verbose=True)
        d = config.to_dict()
        assert d["verbose"] is True


# === Exception Tests ===


class TestExceptions:
    def test_base_exception(self) -> None:
        with pytest.raises(LazySplitterError):
            raise LazySplitterError("test error")

    def test_hierarchy(self) -> None:
        assert issubclass(FileTypeError, LazySplitterError)
        assert issubclass(DetectionError, LazySplitterError)
        assert issubclass(SplitError, LazySplitterError)
        assert issubclass(MergeError, LazySplitterError)
        assert issubclass(ConversionError, LazySplitterError)
        assert issubclass(ConfigError, LazySplitterError)
        assert issubclass(PasswordRequiredError, LazySplitterError)
        assert issubclass(DRMError, LazySplitterError)
        assert issubclass(PluginError, LazySplitterError)
        assert issubclass(CloudError, LazySplitterError)
