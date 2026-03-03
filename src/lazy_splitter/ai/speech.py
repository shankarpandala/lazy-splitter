"""Speech-to-text and audio chapter detection for lazy-splitter.

This module provides the :class:`SpeechDetector` class which wraps speech
recognition and audio analysis capabilities:

* **Transcription** -- convert speech audio to text using OpenAI's Whisper
  (local model via *whisper* or *faster-whisper*).
* **Chapter detection from speech** -- transcribe audio and then scan the
  transcript for chapter announcements (e.g. "Chapter 1", "Part Two").
* **Speaker change detection** -- basic heuristic detection of speaker
  transitions based on silence gaps and energy changes.

All external libraries are imported lazily so the module can be safely
imported even when optional dependencies are absent.
"""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from lazy_splitter.core.exceptions import DetectionError, LazySplitterError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supported engines
# ---------------------------------------------------------------------------

_SUPPORTED_ENGINES = frozenset({"whisper", "auto"})


# ---------------------------------------------------------------------------
# SpeechDetector
# ---------------------------------------------------------------------------

class SpeechDetector:
    """Transcribe audio and detect chapters or speaker changes.

    Parameters
    ----------
    custom_logger:
        Optional :class:`logging.Logger` instance.  If *None*, a module-level
        logger is used.

    Examples
    --------
    >>> detector = SpeechDetector()
    >>> text = detector.transcribe("audiobook.mp3")
    >>> chapters = detector.detect_chapters_from_speech("audiobook.mp3")
    """

    def __init__(self, custom_logger: Optional[logging.Logger] = None) -> None:
        self.logger = custom_logger or logger

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def transcribe(
        self,
        audio_path: str,
        engine: str = "auto",
        *,
        model_size: str = "base",
        language: Optional[str] = None,
    ) -> str:
        """Transcribe an audio file to plain text.

        Parameters
        ----------
        audio_path:
            Path to the audio file (WAV, MP3, FLAC, M4A, OGG, etc.).
        engine:
            Speech recognition engine -- ``"whisper"`` or ``"auto"``.
        model_size:
            Whisper model size (``"tiny"``, ``"base"``, ``"small"``,
            ``"medium"``, ``"large"``).  Larger models are more accurate but
            slower.
        language:
            Optional ISO 639-1 language code (e.g. ``"en"``).  When *None*,
            the language is auto-detected.

        Returns
        -------
        str
            The transcribed text.

        Raises
        ------
        DetectionError
            If the engine is unknown, the file is missing, or transcription
            fails.
        """
        path = Path(audio_path)
        self._validate_path(path)
        engine = self._resolve_engine(engine)

        self.logger.info(
            "Transcribing %s (engine=%s, model_size=%s)",
            audio_path, engine, model_size,
        )

        if engine == "whisper":
            segments = self._transcribe_whisper_segments(
                str(path), model_size=model_size, language=language,
            )
            return " ".join(seg.get("text", "") for seg in segments).strip()

        # Should not reach here since _resolve_engine guarantees "whisper".
        raise DetectionError(f"Unsupported speech engine {engine!r}")

    def detect_chapters_from_speech(
        self,
        audio_path: str,
        *,
        engine: str = "auto",
        model_size: str = "base",
        language: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Transcribe audio and detect chapter announcements in the transcript.

        This method first transcribes the audio with segment-level timestamps,
        then scans for common chapter heading patterns such as "Chapter 1",
        "Part Two", "Section III", etc.

        Parameters
        ----------
        audio_path:
            Path to the audio file.
        engine:
            Speech engine (``"whisper"`` or ``"auto"``).
        model_size:
            Whisper model size.
        language:
            Optional language code for transcription.

        Returns
        -------
        list[dict]
            A list of chapter boundary dictionaries, each containing:
            ``"title"`` (str), ``"start_time"`` (float, seconds),
            ``"end_time"`` (float, seconds), and ``"text"`` (str, the
            matching transcript segment).

        Raises
        ------
        DetectionError
            If transcription fails or no segments can be produced.
        """
        path = Path(audio_path)
        self._validate_path(path)
        engine = self._resolve_engine(engine)

        segments = self._transcribe_whisper_segments(
            str(path), model_size=model_size, language=language,
        )

        if not segments:
            raise DetectionError(
                "No transcript segments were produced.",
                path=audio_path,
            )

        return self._find_chapter_announcements(segments)

    def detect_speakers(
        self,
        audio_path: str,
        *,
        min_silence_ms: int = 700,
        silence_threshold_db: float = -40.0,
    ) -> List[Dict[str, Any]]:
        """Detect potential speaker changes based on silence gaps.

        This is a basic heuristic approach: the audio is scanned for
        silence segments longer than *min_silence_ms*.  Each silence gap
        that exceeds the threshold is reported as a potential speaker
        change point.

        For production-quality speaker diarisation consider dedicated
        libraries such as *pyannote.audio*.

        Parameters
        ----------
        audio_path:
            Path to the audio file.
        min_silence_ms:
            Minimum silence duration (in milliseconds) to consider as a
            speaker change.
        silence_threshold_db:
            Silence threshold in dBFS.  Audio quieter than this is treated
            as silence.

        Returns
        -------
        list[dict]
            A list of speaker change dictionaries, each containing:
            ``"time"`` (float, seconds), ``"silence_duration"`` (float,
            seconds), and ``"speaker_label"`` (str).

        Raises
        ------
        DetectionError
            If *pydub* is not installed or audio analysis fails.
        """
        try:
            from pydub import AudioSegment  # type: ignore[import-untyped]
            from pydub.silence import detect_silence  # type: ignore[import-untyped]
        except ImportError:
            raise DetectionError(
                "The 'pydub' package is required for speaker detection. "
                "Install it with: pip install pydub  "
                "(also ensure 'ffmpeg' is installed on your system)"
            )

        path = Path(audio_path)
        self._validate_path(path)

        self.logger.info("Analysing audio for speaker changes: %s", audio_path)
        try:
            audio = AudioSegment.from_file(str(path))
        except Exception as exc:
            raise DetectionError(
                f"Failed to load audio file: {exc}",
                path=audio_path,
            ) from exc

        try:
            silent_ranges = detect_silence(
                audio,
                min_silence_len=min_silence_ms,
                silence_thresh=silence_threshold_db,
            )
        except Exception as exc:
            raise DetectionError(
                f"Silence detection failed: {exc}",
                path=audio_path,
            ) from exc

        # Build speaker-change points from silence gaps.
        changes: List[Dict[str, Any]] = []
        speaker_index = 1
        for start_ms, end_ms in silent_ranges:
            silence_sec = (end_ms - start_ms) / 1000.0
            change_time = end_ms / 1000.0  # Speaker change after the silence.
            changes.append({
                "time": round(change_time, 3),
                "silence_duration": round(silence_sec, 3),
                "speaker_label": f"Speaker {speaker_index}",
            })
            speaker_index += 1

        self.logger.info(
            "Detected %d potential speaker changes", len(changes),
        )
        return changes

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_path(path: Path) -> None:
        """Raise :class:`DetectionError` if *path* does not exist."""
        if not path.exists():
            raise DetectionError(
                f"Audio file not found: {path}", path=str(path),
            )
        if not path.is_file():
            raise DetectionError(
                f"Path is not a regular file: {path}", path=str(path),
            )

    def _resolve_engine(self, engine: str) -> str:
        """Normalise *engine* and, for ``"auto"``, pick the best available."""
        engine = engine.lower().strip()
        if engine not in _SUPPORTED_ENGINES:
            raise DetectionError(
                f"Unknown speech engine {engine!r}. "
                f"Choose from: {', '.join(sorted(_SUPPORTED_ENGINES))}",
                engine=engine,
            )

        if engine != "auto":
            return engine

        # Auto-select: prefer faster-whisper, then standard whisper.
        try:
            import faster_whisper  # type: ignore[import-untyped] # noqa: F401
            return "whisper"
        except ImportError:
            pass

        try:
            import whisper  # type: ignore[import-untyped] # noqa: F401
            return "whisper"
        except ImportError:
            pass

        raise DetectionError(
            "No speech engine is available. Install one of:\n"
            "  pip install openai-whisper\n"
            "  pip install faster-whisper"
        )

    # -- Whisper transcription -------------------------------------------

    def _transcribe_whisper_segments(
        self,
        audio_path: str,
        *,
        model_size: str = "base",
        language: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Transcribe audio using Whisper and return timestamped segments.

        Attempts *faster-whisper* first; falls back to the standard *whisper*
        package.

        Returns a list of dicts with keys: ``"text"``, ``"start"``, ``"end"``.
        """
        # Try faster-whisper first.
        try:
            return self._transcribe_faster_whisper(
                audio_path, model_size=model_size, language=language,
            )
        except DetectionError:
            raise
        except ImportError:
            pass

        # Fallback to standard whisper.
        try:
            return self._transcribe_standard_whisper(
                audio_path, model_size=model_size, language=language,
            )
        except DetectionError:
            raise
        except ImportError:
            pass

        raise DetectionError(
            "Neither 'faster-whisper' nor 'openai-whisper' is installed. "
            "Install one with:\n"
            "  pip install faster-whisper\n"
            "  pip install openai-whisper"
        )

    def _transcribe_faster_whisper(
        self,
        audio_path: str,
        *,
        model_size: str = "base",
        language: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Transcribe using the faster-whisper library."""
        from faster_whisper import WhisperModel  # type: ignore[import-untyped]

        self.logger.info(
            "Loading faster-whisper model (size=%s)", model_size,
        )
        try:
            model = WhisperModel(model_size, device="auto", compute_type="int8")
            kwargs: Dict[str, Any] = {}
            if language is not None:
                kwargs["language"] = language

            segments_iter, _info = model.transcribe(audio_path, **kwargs)
            segments: List[Dict[str, Any]] = []
            for seg in segments_iter:
                segments.append({
                    "text": seg.text.strip(),
                    "start": seg.start,
                    "end": seg.end,
                })
            return segments
        except Exception as exc:
            raise DetectionError(
                f"faster-whisper transcription failed: {exc}",
                engine="faster-whisper",
                path=audio_path,
            ) from exc

    def _transcribe_standard_whisper(
        self,
        audio_path: str,
        *,
        model_size: str = "base",
        language: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Transcribe using the standard openai-whisper library."""
        import whisper  # type: ignore[import-untyped]

        self.logger.info(
            "Loading whisper model (size=%s)", model_size,
        )
        try:
            model = whisper.load_model(model_size)
            kwargs: Dict[str, Any] = {}
            if language is not None:
                kwargs["language"] = language

            result = model.transcribe(audio_path, **kwargs)
            segments: List[Dict[str, Any]] = []
            for seg in result.get("segments", []):
                segments.append({
                    "text": seg.get("text", "").strip(),
                    "start": seg.get("start", 0.0),
                    "end": seg.get("end", 0.0),
                })
            return segments
        except Exception as exc:
            raise DetectionError(
                f"Whisper transcription failed: {exc}",
                engine="whisper",
                path=audio_path,
            ) from exc

    # -- Chapter announcement detection ----------------------------------

    @staticmethod
    def _find_chapter_announcements(
        segments: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Scan timestamped segments for chapter heading patterns.

        Recognised patterns include:
        * ``Chapter <number/word>``
        * ``Part <number/word>``
        * ``Section <number/word>``
        * ``Book <number/word>``
        * ``Prologue`` / ``Epilogue`` / ``Introduction`` / ``Conclusion``

        Returns a list of chapter dicts with ``title``, ``start_time``,
        ``end_time``, and ``text`` keys.
        """
        chapter_pattern = re.compile(
            r"\b("
            r"chapter\s+[\w\-]+"
            r"|part\s+[\w\-]+"
            r"|section\s+[\w\-]+"
            r"|book\s+[\w\-]+"
            r"|prologue"
            r"|epilogue"
            r"|introduction"
            r"|conclusion"
            r"|afterword"
            r"|preface"
            r"|foreword"
            r")\b",
            re.IGNORECASE,
        )

        chapters: List[Dict[str, Any]] = []
        for seg in segments:
            text = seg.get("text", "")
            match = chapter_pattern.search(text)
            if match:
                title = match.group(1).strip().title()
                chapters.append({
                    "title": title,
                    "start_time": seg.get("start", 0.0),
                    "end_time": seg.get("end", 0.0),
                    "text": text,
                })

        return chapters
