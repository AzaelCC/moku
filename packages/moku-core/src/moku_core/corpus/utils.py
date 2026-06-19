"""Shared corpus loading helpers."""

from __future__ import annotations

from moku_core.corpus.types import CorpusSentence
from moku_core.text.cleaning import clean_corpus_text
from moku_core.text.tokenizers import content_tokens, tokenize


def sentence_record(
    text: str,
    source: str,
    language: str,
    metadata: dict[str, object] | None = None,
) -> CorpusSentence:
    cleaned = clean_corpus_text(text)
    return CorpusSentence(
        source=source,
        language=language,
        text=cleaned,
        tokens=tuple(tokenize(cleaned, language=language)),
        content_tokens=tuple(content_tokens(cleaned, language=language)),
        source_metadata=metadata or {},
    )


def parse_language_pairs(language_pairs: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(pair.strip() for pair in language_pairs if pair.strip())
