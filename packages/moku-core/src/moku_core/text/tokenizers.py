"""Tokenization and content-token extraction."""

from __future__ import annotations

import re
from collections.abc import Collection

from moku_core.exceptions import OptionalDependencyError
from moku_core.text.cleaning import clean_corpus_text
from moku_core.text.languages import is_chinese_language

HAN_CHAR_CLASS = "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
TOKEN_RE = re.compile(
    f"[{HAN_CHAR_CLASS}]+|[^\\W\\d_{HAN_CHAR_CLASS}]+(?:['-][^\\W\\d_{HAN_CHAR_CLASS}]+)?",
    re.UNICODE,
)
CONTENT_TOKEN_RE = re.compile(f"[{HAN_CHAR_CLASS}]|[^\\W_]", re.UNICODE)

# The notebook currently treats all detected content tokens as learning-relevant.
DEFAULT_STOPWORDS: frozenset[str] = frozenset()

_CHINESE_SEGMENTER = None


def _chinese_segmenter():
    global _CHINESE_SEGMENTER
    if _CHINESE_SEGMENTER is None:
        try:
            import pkuseg
        except ImportError as exc:
            raise OptionalDependencyError(
                "Chinese tokenization requires the optional dependency group `moku-core[zh]`."
            ) from exc
        _CHINESE_SEGMENTER = pkuseg.pkuseg()
    return _CHINESE_SEGMENTER


def tokenize(text: str, language: str = "en") -> list[str]:
    """Tokenize cleaned text for a supported language."""
    text = clean_corpus_text(text)
    if is_chinese_language(language):
        return [token.lower() for token in _chinese_segmenter().cut(text) if token.strip()]
    return [match.group(0).lower() for match in TOKEN_RE.finditer(text)]


def content_tokens(
    text: str,
    language: str = "en",
    stopwords: Collection[str] = DEFAULT_STOPWORDS,
) -> list[str]:
    """Return tokens that can participate in retrieval/scoring."""
    return [
        token
        for token in tokenize(text, language=language)
        if token not in stopwords and CONTENT_TOKEN_RE.search(token)
    ]
