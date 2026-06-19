"""Sentence splitting and filtering."""

from __future__ import annotations

import re

from moku_core.text.cleaning import clean_corpus_text
from moku_core.text.tokenizers import tokenize

SENTENCE_BOUNDARY_RE = re.compile(
    r"(?<=[.!?])\s+(?=[\"'({\[]?[A-Z0-9])|(?<=[。！？])\s*"
)


def split_sentences(text: str) -> list[str]:
    """Split cleaned text into candidate sentences."""
    text = clean_corpus_text(text)
    if not text:
        return []
    return [sentence.strip() for sentence in SENTENCE_BOUNDARY_RE.split(text) if sentence.strip()]


def acceptable_sentence(
    sentence: str,
    language: str = "en",
    min_tokens: int = 6,
    max_tokens: int = 32,
) -> bool:
    """Return whether a sentence is in the target token-length range."""
    token_count = len(tokenize(sentence, language=language))
    return min_tokens <= token_count <= max_tokens
