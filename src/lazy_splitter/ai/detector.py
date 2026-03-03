"""AI-powered chapter and section detection for lazy-splitter.

This module provides the :class:`AIDetector` class which wraps several
AI/ML strategies for locating chapter boundaries in plain text:

* **LLM-based detection** – sends text to an LLM (OpenAI, Anthropic, or a
  local Ollama instance) and asks it to identify section boundaries.
* **Topic-modelling detection** – uses TF-IDF + NMF (or CountVectorizer + LDA)
  from *scikit-learn* to segment text by latent topics.
* **Semantic similarity detection** – embeds sliding windows of text with
  *sentence-transformers* and detects large cosine-similarity drops between
  adjacent windows.
* **Auto-sensitivity** – analyses surface features of the text to recommend
  an appropriate detection sensitivity level.

All external libraries are imported lazily inside the methods that need them
so that the module can be imported even when optional dependencies are absent.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from lazy_splitter.ai.models import AIDetectionResult
from lazy_splitter.core.exceptions import DetectionError, LazySplitterError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider defaults
# ---------------------------------------------------------------------------

_DEFAULT_MODELS: Dict[str, str] = {
    "openai": "gpt-4",
    "anthropic": "claude-3-haiku-20240307",
    "ollama": "llama3",
}

_LLM_SYSTEM_PROMPT = (
    "You are a document structure analyst.  Given the following text, identify "
    "all chapter or major section boundaries.  Return ONLY a JSON array where "
    "each element is an object with the keys:\n"
    '  "title" (string) – the chapter/section title,\n'
    '  "start_index" (int) – the character offset where this section starts,\n'
    '  "end_index" (int) – the character offset where this section ends '
    "(exclusive).\n"
    "Return valid JSON with no additional commentary."
)


# ---------------------------------------------------------------------------
# AIDetector
# ---------------------------------------------------------------------------

class AIDetector:
    """Detect chapter / section boundaries using AI and ML techniques.

    Parameters
    ----------
    logger:
        Optional :class:`logging.Logger` instance.  If *None*, a module-level
        logger is used.

    Examples
    --------
    >>> detector = AIDetector()
    >>> result = detector.detect_chapters_llm(text, provider="openai")
    >>> for ch in result.chapters:
    ...     print(ch["title"], ch["start_index"])
    """

    def __init__(self, custom_logger: Optional[logging.Logger] = None) -> None:
        self.logger = custom_logger or logger

    # ------------------------------------------------------------------
    # LLM-based detection
    # ------------------------------------------------------------------

    def detect_chapters_llm(
        self,
        text: str,
        provider: str = "openai",
        model: Optional[str] = None,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 120.0,
    ) -> AIDetectionResult:
        """Use a large-language model to identify chapter boundaries.

        Parameters
        ----------
        text:
            The full document text to analyse.
        provider:
            LLM provider – ``"openai"``, ``"anthropic"``, or ``"ollama"``.
        model:
            Model identifier.  When *None*, a sensible default is chosen for
            the selected *provider*.
        api_key:
            API key for cloud providers.  Falls back to the standard
            environment variables (``OPENAI_API_KEY``, ``ANTHROPIC_API_KEY``).
        base_url:
            Override the base URL (useful for Ollama or compatible proxies).
        timeout:
            Request timeout in seconds.

        Returns
        -------
        AIDetectionResult
            Detection result containing a list of chapter boundary dicts.

        Raises
        ------
        DetectionError
            If the provider is unknown, the API call fails, or the response
            cannot be parsed as valid JSON.
        """
        provider = provider.lower().strip()
        if provider not in _DEFAULT_MODELS:
            raise DetectionError(
                f"Unknown LLM provider {provider!r}. "
                f"Choose from: {', '.join(sorted(_DEFAULT_MODELS))}",
                provider=provider,
            )

        model = model or _DEFAULT_MODELS[provider]
        self.logger.info(
            "Detecting chapters via LLM (provider=%s, model=%s)", provider, model,
        )

        start = time.monotonic()

        if provider == "openai":
            raw = self._call_openai(text, model, api_key=api_key, base_url=base_url, timeout=timeout)
        elif provider == "anthropic":
            raw = self._call_anthropic(text, model, api_key=api_key, timeout=timeout)
        elif provider == "ollama":
            raw = self._call_ollama(text, model, base_url=base_url, timeout=timeout)
        else:
            # Unreachable, but satisfies type checkers.
            raise DetectionError(f"Unsupported provider {provider!r}")

        elapsed = time.monotonic() - start
        chapters = self._parse_llm_response(raw)

        return AIDetectionResult(
            chapters=chapters,
            method="llm",
            model_used=model,
            confidence=0.85,
            processing_time=round(elapsed, 3),
            metadata={"provider": provider, "text_length": len(text)},
        )

    # -- Provider helpers ------------------------------------------------

    def _call_openai(
        self,
        text: str,
        model: str,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 120.0,
    ) -> str:
        """Send a chat-completion request to the OpenAI API.

        Returns the raw assistant message content.
        """
        try:
            import openai  # type: ignore[import-untyped]
        except ImportError:
            raise DetectionError(
                "The 'openai' package is required for OpenAI LLM detection. "
                "Install it with: pip install openai"
            )

        client_kwargs: Dict[str, Any] = {"timeout": timeout}
        if api_key is not None:
            client_kwargs["api_key"] = api_key
        if base_url is not None:
            client_kwargs["base_url"] = base_url

        try:
            client = openai.OpenAI(**client_kwargs)
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _LLM_SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                temperature=0.0,
            )
            content = response.choices[0].message.content or ""
            return content
        except Exception as exc:
            raise DetectionError(
                f"OpenAI API call failed: {exc}",
                provider="openai",
                model=model,
            ) from exc

    def _call_anthropic(
        self,
        text: str,
        model: str,
        *,
        api_key: Optional[str] = None,
        timeout: float = 120.0,
    ) -> str:
        """Send a message to the Anthropic Messages API.

        Returns the raw assistant message text.
        """
        try:
            import anthropic  # type: ignore[import-untyped]
        except ImportError:
            raise DetectionError(
                "The 'anthropic' package is required for Anthropic LLM detection. "
                "Install it with: pip install anthropic"
            )

        client_kwargs: Dict[str, Any] = {"timeout": timeout}
        if api_key is not None:
            client_kwargs["api_key"] = api_key

        try:
            client = anthropic.Anthropic(**client_kwargs)
            response = client.messages.create(
                model=model,
                max_tokens=4096,
                system=_LLM_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": text}],
            )
            # Response content is a list of content blocks.
            return "".join(
                block.text for block in response.content if hasattr(block, "text")
            )
        except Exception as exc:
            raise DetectionError(
                f"Anthropic API call failed: {exc}",
                provider="anthropic",
                model=model,
            ) from exc

    def _call_ollama(
        self,
        text: str,
        model: str,
        *,
        base_url: Optional[str] = None,
        timeout: float = 120.0,
    ) -> str:
        """Send a generate request to a local Ollama instance.

        Returns the raw model response text.
        """
        try:
            import requests  # type: ignore[import-untyped]
        except ImportError:
            raise DetectionError(
                "The 'requests' package is required for Ollama LLM detection. "
                "Install it with: pip install requests"
            )

        url = (base_url or "http://localhost:11434").rstrip("/")
        endpoint = f"{url}/api/chat"

        payload = {
            "model": model,
            "stream": False,
            "messages": [
                {"role": "system", "content": _LLM_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        }

        try:
            resp = requests.post(endpoint, json=payload, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "")
        except Exception as exc:
            raise DetectionError(
                f"Ollama API call failed: {exc}",
                provider="ollama",
                model=model,
            ) from exc

    # -- Response parsing ------------------------------------------------

    @staticmethod
    def _parse_llm_response(raw: str) -> List[Dict[str, Any]]:
        """Extract a JSON chapter array from the raw LLM output.

        The function is tolerant of markdown code fences and leading/trailing
        prose that some models produce.

        Returns
        -------
        list[dict]
            Parsed list of chapter boundary dictionaries.

        Raises
        ------
        DetectionError
            If no valid JSON array can be extracted.
        """
        # Strip markdown code fences if present.
        cleaned = re.sub(r"```(?:json)?\s*", "", raw)
        cleaned = cleaned.strip()

        # Try the whole string first.
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, list):
                return parsed  # type: ignore[return-value]
        except json.JSONDecodeError:
            pass

        # Try to locate the first JSON array in the string.
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
                if isinstance(parsed, list):
                    return parsed  # type: ignore[return-value]
            except json.JSONDecodeError:
                pass

        raise DetectionError(
            "Failed to parse LLM response as a JSON chapter array. "
            f"Raw response (first 500 chars): {raw[:500]!r}"
        )

    # ------------------------------------------------------------------
    # Topic-modelling detection
    # ------------------------------------------------------------------

    def detect_chapters_topic(
        self,
        text: str,
        num_topics: int = 5,
        *,
        method: str = "nmf",
        min_paragraph_length: int = 50,
    ) -> AIDetectionResult:
        """Segment text into chapters by latent topic analysis.

        The text is split into paragraphs; each paragraph is assigned to a
        dominant topic.  Consecutive paragraphs with the same dominant topic
        are grouped, and a change of dominant topic signals a chapter
        boundary.

        Parameters
        ----------
        text:
            The full document text.
        num_topics:
            Number of latent topics to extract.
        method:
            Topic model variant – ``"nmf"`` (TF-IDF + NMF) or ``"lda"``
            (CountVectorizer + LDA).
        min_paragraph_length:
            Paragraphs shorter than this (in characters) are merged into the
            previous paragraph to avoid noise from short lines.

        Returns
        -------
        AIDetectionResult
            Detection result with chapters derived from topic boundaries.

        Raises
        ------
        DetectionError
            If *scikit-learn* is not installed, the text is empty, or model
            fitting fails.
        """
        try:
            from sklearn.decomposition import NMF, LatentDirichletAllocation  # type: ignore[import-untyped]
            from sklearn.feature_extraction.text import (  # type: ignore[import-untyped]
                CountVectorizer,
                TfidfVectorizer,
            )
        except ImportError:
            raise DetectionError(
                "The 'scikit-learn' package is required for topic-based detection. "
                "Install it with: pip install scikit-learn"
            )

        start = time.monotonic()
        method = method.lower().strip()
        if method not in ("nmf", "lda"):
            raise DetectionError(
                f"Unknown topic method {method!r}. Choose 'nmf' or 'lda'."
            )

        # -- Split into paragraphs ------------------------------------------
        paragraphs = self._split_paragraphs(text, min_length=min_paragraph_length)
        if not paragraphs:
            raise DetectionError("No paragraphs found in the provided text.")

        num_topics = min(num_topics, len(paragraphs))

        # -- Vectorise & fit ------------------------------------------------
        try:
            if method == "nmf":
                vectorizer = TfidfVectorizer(
                    max_df=0.95, min_df=1, stop_words="english",
                )
                doc_term = vectorizer.fit_transform(paragraphs)
                model = NMF(n_components=num_topics, random_state=42, max_iter=300)
            else:
                vectorizer = CountVectorizer(
                    max_df=0.95, min_df=1, stop_words="english",
                )
                doc_term = vectorizer.fit_transform(paragraphs)
                model = LatentDirichletAllocation(
                    n_components=num_topics, random_state=42, max_iter=30,
                )

            topic_matrix = model.fit_transform(doc_term)
        except Exception as exc:
            raise DetectionError(
                f"Topic model fitting failed: {exc}", method=method,
            ) from exc

        # -- Identify dominant topic per paragraph --------------------------
        dominant_topics: List[int] = []
        for row in topic_matrix:
            dominant_topics.append(int(row.argmax()))

        # -- Build chapter boundaries from topic changes --------------------
        chapters = self._topics_to_chapters(text, paragraphs, dominant_topics)
        elapsed = time.monotonic() - start

        return AIDetectionResult(
            chapters=chapters,
            method="topic",
            model_used=method.upper(),
            confidence=0.70,
            processing_time=round(elapsed, 3),
            metadata={
                "num_topics": num_topics,
                "paragraph_count": len(paragraphs),
                "topic_method": method,
            },
        )

    # -- Topic helpers ---------------------------------------------------

    @staticmethod
    def _split_paragraphs(text: str, *, min_length: int = 50) -> List[str]:
        """Split *text* on blank lines and merge short fragments.

        Returns a list of non-empty paragraph strings.
        """
        raw_paragraphs = re.split(r"\n\s*\n", text)
        paragraphs: List[str] = []
        for p in raw_paragraphs:
            stripped = p.strip()
            if not stripped:
                continue
            if len(stripped) < min_length and paragraphs:
                # Merge short lines into the previous paragraph.
                paragraphs[-1] = paragraphs[-1] + "\n" + stripped
            else:
                paragraphs.append(stripped)
        return paragraphs

    @staticmethod
    def _topics_to_chapters(
        full_text: str,
        paragraphs: List[str],
        dominant_topics: List[int],
    ) -> List[Dict[str, Any]]:
        """Convert per-paragraph topic labels into chapter boundary dicts.

        Consecutive paragraphs that share the same dominant topic are grouped
        into a single chapter.  Character offsets are computed by locating
        each paragraph inside *full_text*.
        """
        if not paragraphs:
            return []

        chapters: List[Dict[str, Any]] = []
        group_start_idx = 0
        current_topic = dominant_topics[0]

        # Pre-compute character offsets.
        offsets: List[int] = []
        search_from = 0
        for para in paragraphs:
            idx = full_text.find(para[:80], search_from)
            offsets.append(max(idx, search_from))
            if idx >= 0:
                search_from = idx + len(para)

        def _make_title(index: int, para: str) -> str:
            first_line = para.split("\n", 1)[0].strip()
            if len(first_line) <= 80:
                return first_line
            return f"Section {index + 1}"

        for i in range(1, len(paragraphs)):
            if dominant_topics[i] != current_topic:
                # Close previous chapter.
                start_off = offsets[group_start_idx]
                end_off = offsets[i]
                chapters.append({
                    "title": _make_title(len(chapters), paragraphs[group_start_idx]),
                    "start_index": start_off,
                    "end_index": end_off,
                    "topic_id": current_topic,
                })
                group_start_idx = i
                current_topic = dominant_topics[i]

        # Final chapter.
        start_off = offsets[group_start_idx]
        chapters.append({
            "title": _make_title(len(chapters), paragraphs[group_start_idx]),
            "start_index": start_off,
            "end_index": len(full_text),
            "topic_id": current_topic,
        })

        return chapters

    # ------------------------------------------------------------------
    # Semantic similarity detection
    # ------------------------------------------------------------------

    def detect_chapters_semantic(
        self,
        text: str,
        threshold: float = 0.4,
        *,
        window_size: int = 3,
        step_size: int = 1,
        model_name: str = "all-MiniLM-L6-v2",
    ) -> AIDetectionResult:
        """Detect chapters by measuring cosine-similarity drops between
        adjacent sliding windows of text.

        Parameters
        ----------
        text:
            The full document text.
        threshold:
            Minimum cosine-similarity drop between adjacent windows to be
            considered a chapter boundary.  Lower values produce more chapters.
        window_size:
            Number of sentences per sliding window.
        step_size:
            Number of sentences to advance the window each step.
        model_name:
            Sentence-transformer model to use for embeddings.

        Returns
        -------
        AIDetectionResult
            Detection result with chapters derived from similarity drops.

        Raises
        ------
        DetectionError
            If *sentence-transformers* or *numpy* is not installed, or if the
            text contains too few sentences for meaningful analysis.
        """
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]
        except ImportError:
            raise DetectionError(
                "The 'sentence-transformers' package is required for semantic "
                "detection. Install it with: pip install sentence-transformers"
            )

        try:
            import numpy as np  # type: ignore[import-untyped]
        except ImportError:
            raise DetectionError(
                "The 'numpy' package is required for semantic detection. "
                "Install it with: pip install numpy"
            )

        start = time.monotonic()

        # -- Sentence splitting ---------------------------------------------
        sentences = self._split_sentences(text)
        if len(sentences) < window_size * 2:
            raise DetectionError(
                f"Text has only {len(sentences)} sentences; need at least "
                f"{window_size * 2} for meaningful semantic analysis.",
            )

        # -- Build sliding windows ------------------------------------------
        windows: List[str] = []
        window_sentence_indices: List[int] = []
        for i in range(0, len(sentences) - window_size + 1, step_size):
            window_text = " ".join(sentences[i : i + window_size])
            windows.append(window_text)
            window_sentence_indices.append(i)

        if len(windows) < 2:
            raise DetectionError(
                "Not enough text windows for semantic comparison."
            )

        # -- Embed and compute similarities ---------------------------------
        self.logger.info(
            "Encoding %d windows with model %s", len(windows), model_name,
        )
        try:
            encoder = SentenceTransformer(model_name)
            embeddings = encoder.encode(windows, show_progress_bar=False)
        except Exception as exc:
            raise DetectionError(
                f"Sentence-transformer encoding failed: {exc}",
                model=model_name,
            ) from exc

        # Cosine similarity between adjacent windows.
        similarities: List[float] = []
        for i in range(len(embeddings) - 1):
            a = embeddings[i]
            b = embeddings[i + 1]
            norm_a = np.linalg.norm(a)
            norm_b = np.linalg.norm(b)
            if norm_a == 0 or norm_b == 0:
                similarities.append(0.0)
            else:
                sim = float(np.dot(a, b) / (norm_a * norm_b))
                similarities.append(sim)

        # -- Detect drops ---------------------------------------------------
        boundary_indices: List[int] = []
        for i, sim in enumerate(similarities):
            drop = 1.0 - sim
            if drop >= threshold:
                # The boundary is at the start of window i+1.
                boundary_indices.append(window_sentence_indices[i + 1])

        # -- Build chapter dicts -------------------------------------------
        chapters = self._boundaries_to_chapters(text, sentences, boundary_indices)
        elapsed = time.monotonic() - start

        avg_confidence = 1.0 - (
            sum(similarities) / len(similarities) if similarities else 0.0
        )

        return AIDetectionResult(
            chapters=chapters,
            method="semantic",
            model_used=model_name,
            confidence=round(min(max(avg_confidence, 0.0), 1.0), 3),
            processing_time=round(elapsed, 3),
            metadata={
                "threshold": threshold,
                "window_size": window_size,
                "sentence_count": len(sentences),
                "boundary_count": len(boundary_indices),
            },
        )

    # -- Semantic helpers ------------------------------------------------

    @staticmethod
    def _split_sentences(text: str) -> List[str]:
        """Naively split *text* into sentences on common terminators.

        This is deliberately simple so that no NLP library is required.
        """
        raw = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in raw if s.strip()]

    @staticmethod
    def _boundaries_to_chapters(
        full_text: str,
        sentences: List[str],
        boundary_sentence_indices: List[int],
    ) -> List[Dict[str, Any]]:
        """Turn a list of sentence-level boundary indices into chapter dicts
        with character offsets.
        """
        if not sentences:
            return []

        # Pre-compute character offsets for each sentence.
        char_offsets: List[int] = []
        search_from = 0
        for sent in sentences:
            idx = full_text.find(sent[:60], search_from)
            char_offsets.append(max(idx, search_from))
            if idx >= 0:
                search_from = idx + len(sent)

        all_boundaries = [0] + sorted(set(boundary_sentence_indices)) + [len(sentences)]

        chapters: List[Dict[str, Any]] = []
        for i in range(len(all_boundaries) - 1):
            sent_start = all_boundaries[i]
            sent_end = all_boundaries[i + 1]
            if sent_start >= len(sentences):
                break

            start_off = char_offsets[sent_start]
            if sent_end < len(sentences):
                end_off = char_offsets[sent_end]
            else:
                end_off = len(full_text)

            # Use the first sentence as the title (truncated).
            first_sentence = sentences[sent_start]
            title = first_sentence[:80].strip()
            if len(first_sentence) > 80:
                title += "..."

            chapters.append({
                "title": title if title else f"Section {i + 1}",
                "start_index": start_off,
                "end_index": end_off,
            })

        return chapters

    # ------------------------------------------------------------------
    # Auto-sensitivity
    # ------------------------------------------------------------------

    def auto_sensitivity(
        self,
        text: str,
        file_type: str = "text",
    ) -> str:
        """Recommend an optimal detection sensitivity based on text features.

        The function analyses several surface-level features of the text:

        * **Heading frequency** – how often lines match common heading
          patterns (``Chapter X``, ``PART II``, all-caps lines, etc.).
        * **Length** – shorter documents benefit from higher sensitivity.
        * **Paragraph variance** – documents with highly varied paragraph
          lengths suggest explicit structural markers.

        Parameters
        ----------
        text:
            The full document text.
        file_type:
            Canonical file type (``"pdf"``, ``"epub"``, ``"text"``, etc.).

        Returns
        -------
        str
            One of ``"low"``, ``"medium"``, or ``"high"``.
        """
        if not text or not text.strip():
            return "medium"

        lines = text.splitlines()
        total_lines = max(len(lines), 1)
        total_chars = len(text)

        # -- Heading frequency ----------------------------------------------
        heading_pattern = re.compile(
            r"^\s*("
            r"chapter\s+\w+"
            r"|part\s+\w+"
            r"|section\s+\w+"
            r"|\d+[.)]\s+\S"
            r"|[A-Z][A-Z\s]{4,}$"
            r")",
            re.IGNORECASE | re.MULTILINE,
        )
        heading_count = len(heading_pattern.findall(text))
        heading_ratio = heading_count / total_lines

        # -- Paragraph length variance --------------------------------------
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        if len(paragraphs) > 1:
            lengths = [len(p) for p in paragraphs]
            mean_len = sum(lengths) / len(lengths)
            variance = sum((l - mean_len) ** 2 for l in lengths) / len(lengths)
        else:
            variance = 0.0

        # -- Decision logic -------------------------------------------------
        score = 0.0

        # Many explicit headings -> low sensitivity is fine.
        if heading_ratio > 0.05:
            score -= 1.0
        elif heading_ratio > 0.02:
            score -= 0.5

        # Short documents need more sensitive detection.
        if total_chars < 5000:
            score += 1.0
        elif total_chars < 20000:
            score += 0.5

        # High paragraph length variance suggests clear structure.
        if variance > 10000:
            score -= 0.5

        # PDF / EPUB often have embedded structural hints.
        if file_type in ("pdf", "epub"):
            score -= 0.5

        if score >= 0.5:
            return "high"
        elif score <= -0.5:
            return "low"
        return "medium"
