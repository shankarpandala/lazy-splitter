"""LLM-based text summarisation for lazy-splitter.

This module provides the :class:`ChapterSummarizer` class which uses large
language models to:

* Summarise a chapter or section of text.
* Generate a descriptive title for an untitled section.
* Batch-summarise multiple chapters in a single pass.

Supported LLM providers mirror those in :mod:`lazy_splitter.ai.detector`:
``"openai"`` (GPT), ``"anthropic"`` (Claude), and ``"ollama"`` (local models).

All external libraries are imported lazily inside the methods that need them
so the module can be imported even when optional dependencies are absent.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from lazy_splitter.ai.models import SummaryResult
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


# ---------------------------------------------------------------------------
# ChapterSummarizer
# ---------------------------------------------------------------------------

class ChapterSummarizer:
    """Summarise text and generate titles using LLM providers.

    Parameters
    ----------
    custom_logger:
        Optional :class:`logging.Logger` instance.  If *None*, a module-level
        logger is used.

    Examples
    --------
    >>> summarizer = ChapterSummarizer()
    >>> result = summarizer.summarize(chapter_text, provider="openai")
    >>> print(result.summary)
    """

    def __init__(self, custom_logger: Optional[logging.Logger] = None) -> None:
        self.logger = custom_logger or logger

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def summarize(
        self,
        text: str,
        provider: str = "openai",
        model: Optional[str] = None,
        max_length: int = 200,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 120.0,
    ) -> SummaryResult:
        """Summarise a chapter or block of text using an LLM.

        Parameters
        ----------
        text:
            The text to summarise.
        provider:
            LLM provider – ``"openai"``, ``"anthropic"``, or ``"ollama"``.
        model:
            Model identifier.  When *None*, a sensible default is chosen for
            the selected *provider*.
        max_length:
            Target maximum word count for the summary.
        api_key:
            API key for cloud providers (falls back to environment variables).
        base_url:
            Override the base URL (useful for Ollama or compatible proxies).
        timeout:
            Request timeout in seconds.

        Returns
        -------
        SummaryResult
            The generated summary with metadata.

        Raises
        ------
        DetectionError
            If the provider is unknown or the LLM call fails.
        """
        provider = provider.lower().strip()
        model = model or _DEFAULT_MODELS.get(provider, "")
        self._validate_provider(provider)

        prompt = (
            f"Summarise the following text in no more than {max_length} words. "
            "Write a clear, concise summary that captures the main ideas.\n\n"
            f"{text}"
        )

        start = time.monotonic()
        raw = self._call_llm(
            prompt,
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            system_message="You are a concise text summariser. Return only the summary, no preamble.",
        )
        elapsed = time.monotonic() - start

        return SummaryResult(
            summary=raw.strip(),
            title="",
            model_used=model,
            metadata={
                "provider": provider,
                "max_length": max_length,
                "input_word_count": len(text.split()),
                "processing_time": round(elapsed, 3),
            },
        )

    def summarize_batch(
        self,
        texts: List[str],
        provider: str = "openai",
        model: Optional[str] = None,
        *,
        max_length: int = 200,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 120.0,
    ) -> List[SummaryResult]:
        """Summarise multiple chapters sequentially.

        This is a convenience wrapper that calls :meth:`summarize` for each
        text in *texts*.  A future version may batch requests for providers
        that support it.

        Parameters
        ----------
        texts:
            List of text blocks to summarise.
        provider:
            LLM provider.
        model:
            Model identifier (or *None* for the default).
        max_length:
            Target maximum word count per summary.
        api_key:
            API key for cloud providers.
        base_url:
            Override the base URL.
        timeout:
            Per-request timeout in seconds.

        Returns
        -------
        list[SummaryResult]
            One :class:`SummaryResult` per input text.
        """
        results: List[SummaryResult] = []
        for i, text in enumerate(texts):
            self.logger.info("Summarising text %d/%d", i + 1, len(texts))
            result = self.summarize(
                text,
                provider=provider,
                model=model,
                max_length=max_length,
                api_key=api_key,
                base_url=base_url,
                timeout=timeout,
            )
            results.append(result)
        return results

    def generate_title(
        self,
        text: str,
        provider: str = "openai",
        model: Optional[str] = None,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 120.0,
    ) -> str:
        """Generate a short, descriptive title for a block of text.

        Parameters
        ----------
        text:
            The text for which a title is needed.
        provider:
            LLM provider.
        model:
            Model identifier (or *None* for the default).
        api_key:
            API key for cloud providers.
        base_url:
            Override the base URL.
        timeout:
            Request timeout in seconds.

        Returns
        -------
        str
            A short title string (typically 3-10 words).

        Raises
        ------
        DetectionError
            If the LLM call fails.
        """
        provider = provider.lower().strip()
        model = model or _DEFAULT_MODELS.get(provider, "")
        self._validate_provider(provider)

        prompt = (
            "Generate a short, descriptive title (3 to 10 words) for the "
            "following text.  Return ONLY the title, with no quotes or "
            "additional commentary.\n\n"
            f"{text}"
        )

        raw = self._call_llm(
            prompt,
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            system_message="You are a concise title generator. Return only the title.",
        )

        # Strip surrounding quotes that some models add.
        title = raw.strip().strip("\"'").strip()
        return title

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_provider(provider: str) -> None:
        """Raise :class:`DetectionError` if *provider* is not supported."""
        if provider not in _DEFAULT_MODELS:
            raise DetectionError(
                f"Unknown LLM provider {provider!r}. "
                f"Choose from: {', '.join(sorted(_DEFAULT_MODELS))}",
                provider=provider,
            )

    def _call_llm(
        self,
        prompt: str,
        *,
        provider: str,
        model: str,
        api_key: Optional[str],
        base_url: Optional[str],
        timeout: float,
        system_message: str,
    ) -> str:
        """Dispatch an LLM request to the appropriate provider.

        Returns the raw text response from the model.
        """
        if provider == "openai":
            return self._call_openai(prompt, model, system_message, api_key=api_key, base_url=base_url, timeout=timeout)
        elif provider == "anthropic":
            return self._call_anthropic(prompt, model, system_message, api_key=api_key, timeout=timeout)
        elif provider == "ollama":
            return self._call_ollama(prompt, model, system_message, base_url=base_url, timeout=timeout)
        else:
            raise DetectionError(f"Unsupported provider {provider!r}")

    # -- Provider implementations ----------------------------------------

    @staticmethod
    def _call_openai(
        prompt: str,
        model: str,
        system_message: str,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 120.0,
    ) -> str:
        """Send a chat-completion request to the OpenAI API."""
        try:
            import openai  # type: ignore[import-untyped]
        except ImportError:
            raise DetectionError(
                "The 'openai' package is required for OpenAI summarisation. "
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
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            raise DetectionError(
                f"OpenAI API call failed: {exc}",
                provider="openai",
                model=model,
            ) from exc

    @staticmethod
    def _call_anthropic(
        prompt: str,
        model: str,
        system_message: str,
        *,
        api_key: Optional[str] = None,
        timeout: float = 120.0,
    ) -> str:
        """Send a message to the Anthropic Messages API."""
        try:
            import anthropic  # type: ignore[import-untyped]
        except ImportError:
            raise DetectionError(
                "The 'anthropic' package is required for Anthropic summarisation. "
                "Install it with: pip install anthropic"
            )

        client_kwargs: Dict[str, Any] = {"timeout": timeout}
        if api_key is not None:
            client_kwargs["api_key"] = api_key

        try:
            client = anthropic.Anthropic(**client_kwargs)
            response = client.messages.create(
                model=model,
                max_tokens=1024,
                system=system_message,
                messages=[{"role": "user", "content": prompt}],
            )
            return "".join(
                block.text for block in response.content if hasattr(block, "text")
            )
        except Exception as exc:
            raise DetectionError(
                f"Anthropic API call failed: {exc}",
                provider="anthropic",
                model=model,
            ) from exc

    @staticmethod
    def _call_ollama(
        prompt: str,
        model: str,
        system_message: str,
        *,
        base_url: Optional[str] = None,
        timeout: float = 120.0,
    ) -> str:
        """Send a generate request to a local Ollama instance."""
        try:
            import requests  # type: ignore[import-untyped]
        except ImportError:
            raise DetectionError(
                "The 'requests' package is required for Ollama summarisation. "
                "Install it with: pip install requests"
            )

        url = (base_url or "http://localhost:11434").rstrip("/")
        endpoint = f"{url}/api/chat"

        payload = {
            "model": model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
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
