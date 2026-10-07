"""A5. Language detection (ms, en, mixed) and YAKE keyword extraction."""

from __future__ import annotations

import yake
from langdetect import DetectorFactory, detect_langs
from langdetect.lang_detect_exception import LangDetectException

DetectorFactory.seed = 0  # langdetect is random without a seed

_MALAY = {"ms", "id"}  # langdetect confuses Malay and Indonesian
MIXED_MIN_PROB = 0.3
MIN_WORDS = 20


def _map(code: str) -> str:
    return "ms" if code in _MALAY else code


def detect_lang(text: str) -> str:
    """Return "ms", "en", or "mixed". Anything undetectable or other falls back to "en"."""
    try:
        langs = detect_langs(text)
    except LangDetectException:
        return "en"
    if not langs:
        return "en"
    if len(langs) >= 2:
        a, b = langs[0], langs[1]
        if (
            {_map(a.lang), _map(b.lang)} == {"ms", "en"}
            and a.prob > MIXED_MIN_PROB
            and b.prob > MIXED_MIN_PROB
        ):
            return "mixed"
    top = _map(langs[0].lang)
    return top if top in ("ms", "en") else "en"


def extract_keywords(text: str, lang: str, top_k: int = 10) -> list[str]:
    """YAKE top_k keywords (up to bigrams), lowercased, deduplicated, in YAKE's order."""
    if len(text.split()) < MIN_WORDS:
        return []
    # yake ships no Malay stopword list ("ms" falls back to none); Indonesian is close enough.
    lan = "id" if lang in ("ms", "mixed") else "en"
    # yake 0.7 names the option dedup_lim; dedupLim would be silently ignored.
    extractor = yake.KeywordExtractor(lan=lan, n=2, dedup_lim=0.9, top=top_k)
    out: list[str] = []
    for kw, _score in extractor.extract_keywords(text):
        kw = kw.lower()
        if kw not in out:
            out.append(kw)
    return out[:top_k]
