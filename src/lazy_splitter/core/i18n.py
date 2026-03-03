"""Internationalization support for chapter heading detection.

Provides regex patterns for recognising chapter / part / section headings in
20+ languages.  The patterns are intentionally broad so that detection has high
recall; confidence scoring downstream can then prune false positives.

Usage::

    from lazy_splitter.core.i18n import get_patterns

    # Auto-detect system locale
    patterns = get_patterns()

    # Explicit language
    patterns = get_patterns("de")
"""

from __future__ import annotations

import locale
import re
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Chapter heading patterns keyed by ISO 639-1 language code
# ---------------------------------------------------------------------------
# Each value is a list of regex strings compiled with ``re.IGNORECASE`` and
# ``re.MULTILINE``.  Groups are included where they may help callers extract
# the chapter number or title.

CHAPTER_PATTERNS: Dict[str, List[str]] = {
    # --- English ---
    "en": [
        r"^Chapter\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^CHAPTER\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Part\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^PART\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Section\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Prologue[\s:.\-]*(.*?)$",
        r"^Epilogue[\s:.\-]*(.*?)$",
        r"^Introduction[\s:.\-]*(.*?)$",
        r"^Appendix\s*([A-Z\d]*)[\s:.\-]*(.*?)$",
    ],
    # --- Spanish ---
    "es": [
        r"^Cap[ií]tulo\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^CAP[IÍ]TULO\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Parte\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Secci[oó]n\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Pr[oó]logo[\s:.\-]*(.*?)$",
        r"^Ep[ií]logo[\s:.\-]*(.*?)$",
        r"^Introducci[oó]n[\s:.\-]*(.*?)$",
        r"^Ap[eé]ndice\s*([A-Z\d]*)[\s:.\-]*(.*?)$",
    ],
    # --- French ---
    "fr": [
        r"^Chapitre\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^CHAPITRE\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Partie\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Section\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Prologue[\s:.\-]*(.*?)$",
        r"^[EÉ]pilogue[\s:.\-]*(.*?)$",
        r"^Introduction[\s:.\-]*(.*?)$",
        r"^Annexe\s*([A-Z\d]*)[\s:.\-]*(.*?)$",
    ],
    # --- German ---
    "de": [
        r"^Kapitel\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^KAPITEL\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Teil\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Abschnitt\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Einleitung[\s:.\-]*(.*?)$",
        r"^Anhang\s*([A-Z\d]*)[\s:.\-]*(.*?)$",
    ],
    # --- Italian ---
    "it": [
        r"^Capitolo\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^CAPITOLO\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Parte\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Sezione\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Prologo[\s:.\-]*(.*?)$",
        r"^Epilogo[\s:.\-]*(.*?)$",
        r"^Introduzione[\s:.\-]*(.*?)$",
        r"^Appendice\s*([A-Z\d]*)[\s:.\-]*(.*?)$",
    ],
    # --- Portuguese ---
    "pt": [
        r"^Cap[ií]tulo\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^CAP[IÍ]TULO\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Parte\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Se[cç][aã]o\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Pr[oó]logo[\s:.\-]*(.*?)$",
        r"^Ep[ií]logo[\s:.\-]*(.*?)$",
        r"^Introdu[cç][aã]o[\s:.\-]*(.*?)$",
        r"^Ap[eê]ndice\s*([A-Z\d]*)[\s:.\-]*(.*?)$",
    ],
    # --- Dutch ---
    "nl": [
        r"^Hoofdstuk\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^HOOFDSTUK\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Deel\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Paragraaf\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Inleiding[\s:.\-]*(.*?)$",
        r"^Bijlage\s*([A-Z\d]*)[\s:.\-]*(.*?)$",
    ],
    # --- Russian ---
    "ru": [
        r"^[Гг]лава\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^ГЛАВА\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^[Чч]асть\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^[Рр]аздел\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^[Вв]ведение[\s:.\-]*(.*?)$",
        r"^[Зз]аключение[\s:.\-]*(.*?)$",
        r"^[Пп]риложение\s*([A-ZА-Я\d]*)[\s:.\-]*(.*?)$",
    ],
    # --- Japanese ---
    "ja": [
        r"^第\s*([一二三四五六七八九十百\d]+)\s*章[\s:.\-]*(.*?)$",
        r"^第\s*([一二三四五六七八九十百\d]+)\s*部[\s:.\-]*(.*?)$",
        r"^第\s*([一二三四五六七八九十百\d]+)\s*節[\s:.\-]*(.*?)$",
        r"^第\s*([一二三四五六七八九十百\d]+)\s*編[\s:.\-]*(.*?)$",
        r"^序章[\s:.\-]*(.*?)$",
        r"^終章[\s:.\-]*(.*?)$",
        r"^はじめに[\s:.\-]*(.*?)$",
        r"^付録\s*([A-Z\d]*)[\s:.\-]*(.*?)$",
    ],
    # --- Chinese (Simplified & Traditional) ---
    "zh": [
        r"^第\s*([一二三四五六七八九十百千\d]+)\s*章[\s:.\-]*(.*?)$",
        r"^第\s*([一二三四五六七八九十百千\d]+)\s*[部卷][\s:.\-]*(.*?)$",
        r"^第\s*([一二三四五六七八九十百千\d]+)\s*[节節][\s:.\-]*(.*?)$",
        r"^序[言章][\s:.\-]*(.*?)$",
        r"^[终終]章[\s:.\-]*(.*?)$",
        r"^前言[\s:.\-]*(.*?)$",
        r"^引言[\s:.\-]*(.*?)$",
        r"^附[录錄]\s*([A-Z\d]*)[\s:.\-]*(.*?)$",
    ],
    # --- Korean ---
    "ko": [
        r"^제\s*(\d+)\s*장[\s:.\-]*(.*?)$",
        r"^제\s*(\d+)\s*부[\s:.\-]*(.*?)$",
        r"^제\s*(\d+)\s*절[\s:.\-]*(.*?)$",
        r"^서장[\s:.\-]*(.*?)$",
        r"^종장[\s:.\-]*(.*?)$",
        r"^서론[\s:.\-]*(.*?)$",
        r"^부록\s*([A-Z\d]*)[\s:.\-]*(.*?)$",
    ],
    # --- Arabic ---
    "ar": [
        r"^الفصل\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^الباب\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^الجزء\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^المقدمة[\s:.\-]*(.*?)$",
        r"^الخاتمة[\s:.\-]*(.*?)$",
        r"^الملحق\s*([A-Z\d]*)[\s:.\-]*(.*?)$",
    ],
    # --- Hindi ---
    "hi": [
        r"^अध्याय\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^भाग\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^खण्ड\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^प्रस्तावना[\s:.\-]*(.*?)$",
        r"^उपसंहार[\s:.\-]*(.*?)$",
        r"^परिशिष्ट\s*([A-Z\d]*)[\s:.\-]*(.*?)$",
    ],
    # --- Polish ---
    "pl": [
        r"^Rozdzia[lł]\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^ROZDZIA[LŁ]\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Cz[eę][sś][cć]\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Wst[eę]p[\s:.\-]*(.*?)$",
        r"^Zako[nń]czenie[\s:.\-]*(.*?)$",
        r"^Za[lł][aą]cznik\s*([A-Z\d]*)[\s:.\-]*(.*?)$",
    ],
    # --- Swedish ---
    "sv": [
        r"^Kapitel\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^KAPITEL\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Del\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Avsnitt\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Inledning[\s:.\-]*(.*?)$",
        r"^Bilaga\s*([A-Z\d]*)[\s:.\-]*(.*?)$",
    ],
    # --- Danish ---
    "da": [
        r"^Kapitel\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^KAPITEL\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Del\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Afsnit\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Indledning[\s:.\-]*(.*?)$",
        r"^Bilag\s*([A-Z\d]*)[\s:.\-]*(.*?)$",
    ],
    # --- Norwegian ---
    "no": [
        r"^Kapittel\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^KAPITTEL\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Del\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Avsnitt\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Innledning[\s:.\-]*(.*?)$",
        r"^Vedlegg\s*([A-Z\d]*)[\s:.\-]*(.*?)$",
    ],
    # --- Finnish ---
    "fi": [
        r"^Luku\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^LUKU\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Osa\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Jakso\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Johdanto[\s:.\-]*(.*?)$",
        r"^Liite\s*([A-Z\d]*)[\s:.\-]*(.*?)$",
    ],
    # --- Czech ---
    "cs": [
        r"^Kapitola\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^KAPITOLA\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^[CČ][aá]st\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^[ÚU]vod[\s:.\-]*(.*?)$",
        r"^Z[aá]v[eě]r[\s:.\-]*(.*?)$",
        r"^P[rř][ií]loha\s*([A-Z\d]*)[\s:.\-]*(.*?)$",
    ],
    # --- Turkish ---
    "tr": [
        r"^B[oö]l[uü]m\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^B[OÖ]L[UÜ]M\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^K[iı]s[iı]m\s+(\d+|[IVXLCDM]+)[\s:.\-]*(.*?)$",
        r"^Giri[sş][\s:.\-]*(.*?)$",
        r"^Sonu[cç][\s:.\-]*(.*?)$",
        r"^Ek\s*([A-Z\d]*)[\s:.\-]*(.*?)$",
    ],
}

# ---------------------------------------------------------------------------
# Generic / fallback numeric patterns (language-agnostic)
# ---------------------------------------------------------------------------
_GENERIC_PATTERNS: List[str] = [
    r"^(\d+)\.\s+(.+)$",                         # "1. Introduction"
    r"^(\d+)\s*[-:]\s*(.+)$",                     # "1 - Introduction"
    r"^([IVXLCDM]+)\.\s+(.+)$",                   # "IV. The Quest"
    r"^([IVXLCDM]+)\s*[-:]\s*(.+)$",              # "IV - The Quest"
]


def _detect_system_language() -> str:
    """Detect the system language from the locale.

    Returns:
        A two-letter ISO 639-1 language code, defaulting to ``"en"`` if
        detection fails.
    """
    try:
        lang, _ = locale.getdefaultlocale()
        if lang:
            # lang looks like "en_US", "de_DE", etc.
            code = lang.split("_")[0].lower()
            if code in CHAPTER_PATTERNS:
                return code
    except (ValueError, AttributeError):
        pass
    return "en"


def get_patterns(language: Optional[str] = None) -> List[str]:
    """Return compiled-ready regex pattern strings for chapter headings.

    Parameters:
        language:
            Two-letter ISO 639-1 language code (e.g. ``"en"``, ``"de"``).
            When *None*, the system locale is used with a fallback to English.

    Returns:
        A combined list of language-specific patterns followed by the generic
        numeric patterns that apply across all languages.

    Raises:
        ValueError: If *language* is provided but not recognised.

    Example::

        import re
        from lazy_splitter.core.i18n import get_patterns

        for pattern in get_patterns("fr"):
            if re.match(pattern, line, re.IGNORECASE | re.MULTILINE):
                print("Chapter heading found!")
    """
    if language is None:
        language = _detect_system_language()

    language = language.lower()

    if language not in CHAPTER_PATTERNS:
        raise ValueError(
            f"Unsupported language code {language!r}. "
            f"Supported: {sorted(CHAPTER_PATTERNS.keys())}"
        )

    return list(CHAPTER_PATTERNS[language]) + list(_GENERIC_PATTERNS)


def get_all_patterns() -> Dict[str, List[str]]:
    """Return the full patterns dictionary (read-only copy).

    Returns:
        A dictionary mapping language codes to their pattern lists.
    """
    return {lang: list(pats) + list(_GENERIC_PATTERNS) for lang, pats in CHAPTER_PATTERNS.items()}


def supported_languages() -> List[str]:
    """Return a sorted list of supported language codes.

    Returns:
        Sorted list of two-letter ISO 639-1 codes.
    """
    return sorted(CHAPTER_PATTERNS.keys())
