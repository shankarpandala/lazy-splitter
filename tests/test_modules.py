"""Tests for lazy_splitter module imports and basic structure."""
from __future__ import annotations

import pytest


class TestPackageImport:
    """Test that the main package and all subpackages import cleanly."""

    def test_main_package(self) -> None:
        import lazy_splitter
        assert hasattr(lazy_splitter, "__version__")
        assert lazy_splitter.__version__ == "0.3.0"

    def test_core_import(self) -> None:
        from lazy_splitter.core import models, utils, exceptions, config, i18n, base
        assert hasattr(models, "Chapter")
        assert hasattr(models, "DetectionResult")
        assert hasattr(utils, "sanitize_filename")
        assert hasattr(exceptions, "LazySplitterError")

    def test_pdf_import(self) -> None:
        from lazy_splitter.pdf import PDFDetector, PDFSplitter
        assert PDFDetector is not None
        assert PDFSplitter is not None

    def test_epub_import(self) -> None:
        from lazy_splitter.epub import EpubDetector, EpubSplitter
        assert EpubDetector is not None
        assert EpubSplitter is not None

    def test_video_models_import(self) -> None:
        from lazy_splitter.video.models import VideoSegment, VideoInfo, VideoSplitOptions
        seg = VideoSegment(title="Test", start_time=0.0, end_time=10.0)
        assert seg.duration == pytest.approx(10.0)

    def test_audio_models_import(self) -> None:
        from lazy_splitter.audio.models import AudioSegment, AudioInfo, AudioSplitOptions
        seg = AudioSegment(title="Track", start_time=0.0, end_time=60.0)
        assert seg.duration == pytest.approx(60.0)

    def test_document_models_import(self) -> None:
        from lazy_splitter.document.models import DocumentSection, DocumentInfo, FileType
        assert FileType.DOCX is not None
        assert FileType.MARKDOWN is not None

    def test_image_models_import(self) -> None:
        from lazy_splitter.image.models import ImageFrame, ImageInfo, ImageSplitOptions
        frame = ImageFrame(title="Frame 1", index=0, width=100, height=100, format="png")
        assert frame.width == 100

    def test_merge_import(self) -> None:
        from lazy_splitter.merge import PDFMerger, EpubMerger, VideoMerger, AudioMerger, DocumentMerger
        assert PDFMerger is not None

    def test_convert_models_import(self) -> None:
        from lazy_splitter.convert.models import ConversionOptions, CONVERSION_MAP
        assert "pdf" in CONVERSION_MAP
        assert "mp4" in CONVERSION_MAP

    def test_batch_models_import(self) -> None:
        from lazy_splitter.batch.models import BatchResult, BatchFileResult, PipelineResult
        result = BatchResult()
        assert result.total_files == 0

    def test_cloud_models_import(self) -> None:
        from lazy_splitter.cloud.models import CloudFile, SyncResult
        assert CloudFile is not None

    def test_ai_models_import(self) -> None:
        from lazy_splitter.ai.models import AIDetectionResult, OCRResult, SummaryResult
        assert AIDetectionResult is not None

    def test_plugins_import(self) -> None:
        from lazy_splitter.plugins import (
            Plugin, StrategyPlugin, FileTypePlugin, OutputPlugin,
            HookPlugin, PluginManager, HookManager,
            register_strategy, register_file_handler,
        )
        assert PluginManager is not None
        assert HookManager is not None


class TestPluginSystem:
    """Test the plugin registration and hook system."""

    def test_strategy_registration(self) -> None:
        from lazy_splitter.plugins.base import register_strategy, get_registered_strategies

        @register_strategy("test_strategy_123")
        class TestDetector:
            def detect(self, path, **kwargs):  # type: ignore
                return None

        strategies = get_registered_strategies()
        assert "test_strategy_123" in strategies

    def test_hook_manager(self) -> None:
        from lazy_splitter.plugins.hooks import HookManager

        hooks = HookManager()
        results = []

        def callback(**kwargs):  # type: ignore
            results.append(kwargs)

        hooks.register_hook("pre_split", callback)
        hooks.emit("pre_split", file_path="/test.pdf")
        assert len(results) == 1
        assert results[0]["file_path"] == "/test.pdf"

    def test_hook_manager_clear(self) -> None:
        from lazy_splitter.plugins.hooks import HookManager

        hooks = HookManager()
        hooks.register_hook("pre_split", lambda **kw: None)
        assert len(hooks.get_hooks("pre_split")) == 1
        hooks.clear("pre_split")
        assert len(hooks.get_hooks("pre_split")) == 0

    def test_hook_invalid_event(self) -> None:
        from lazy_splitter.plugins.hooks import HookManager

        hooks = HookManager()
        with pytest.raises(ValueError):
            hooks.register_hook("invalid_event", lambda **kw: None)

    def test_plugin_manager_discover(self) -> None:
        from lazy_splitter.plugins.manager import PluginManager

        pm = PluginManager()
        discovered = pm.discover_plugins()
        # May or may not find plugins, but shouldn't error
        assert isinstance(discovered, list)


class TestBatchPipeline:
    """Test the batch pipeline construction."""

    def test_pipeline_creation(self) -> None:
        from lazy_splitter.batch.pipeline import Pipeline

        p = Pipeline()
        p.add_step("detect", strategy="hybrid")
        p.add_step("split", output_dir="/tmp/output")
        assert len(p._steps) == 2

    def test_pipeline_from_dict(self) -> None:
        from lazy_splitter.batch.pipeline import Pipeline

        config = {
            "steps": [
                {"operation": "detect", "strategy": "hybrid"},
                {"operation": "split"},
            ]
        }
        p = Pipeline.from_dict(config)
        assert len(p._steps) == 2


class TestConversionMap:
    """Test the format conversion mapping."""

    def test_pdf_conversions(self) -> None:
        from lazy_splitter.convert.converter import FormatConverter

        conv = FormatConverter()
        supported = conv.get_supported_conversions()
        assert "pdf" in supported
        assert "png" in supported["pdf"] or "txt" in supported["pdf"]

    def test_can_convert(self) -> None:
        from lazy_splitter.convert.converter import FormatConverter

        conv = FormatConverter()
        supported = conv.get_supported_conversions()
        assert "mp3" in supported.get("mp4", [])
        assert "xyz" not in supported.get("pdf", [])


class TestCueParser:
    """Test the CUE sheet parser."""

    def test_parse_cue_basic(self) -> None:
        import tempfile
        from lazy_splitter.audio.cue_parser import parse_cue

        cue_content = '''PERFORMER "Test Artist"
TITLE "Test Album"
FILE "audio.flac" WAVE
  TRACK 01 AUDIO
    TITLE "Track One"
    PERFORMER "Test Artist"
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    TITLE "Track Two"
    INDEX 01 03:45:00
  TRACK 03 AUDIO
    TITLE "Track Three"
    INDEX 01 07:30:25
'''
        with tempfile.NamedTemporaryFile(mode="w", suffix=".cue", delete=False) as f:
            f.write(cue_content)
            cue_path = f.name

        try:
            from pathlib import Path
            segments = parse_cue(Path(cue_path))
            assert len(segments) == 3
            assert segments[0].title == "Track One"
            assert segments[0].start_time == pytest.approx(0.0)
            assert segments[1].start_time == pytest.approx(225.0)  # 3*60+45
            assert segments[2].start_time == pytest.approx(450.0 + 25 / 75)  # 7*60+30 + 25 frames
        finally:
            import os
            os.unlink(cue_path)
