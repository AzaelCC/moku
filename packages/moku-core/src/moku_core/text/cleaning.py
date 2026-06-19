"""Corpus-specific text cleaning."""

from __future__ import annotations

import re

SUBTITLE_OVERRIDE_RE = re.compile(r"\{\\[^}]*\}")
SUBTITLE_ESCAPE_RE = re.compile(r"\\[A-Za-z]+")


def clean_corpus_text(text: str) -> str:
    """Normalize subtitle markup and whitespace without changing sentence content."""
    text = SUBTITLE_OVERRIDE_RE.sub(" ", text)
    text = SUBTITLE_ESCAPE_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_wiki40b_text(text: str) -> str:
    """Remove Wiki40B section markers before generic corpus cleaning."""
    text = re.sub(r"_START_[A-Z]+_\s*[^.!?_\n]{1,80}\s*_END_[A-Z]+_", " ", text)
    text = re.sub(r"_(?:START|END)_[A-Z]+_", " ", text)
    text = text.replace("_NEWLINE_", " ")
    return clean_corpus_text(text)
