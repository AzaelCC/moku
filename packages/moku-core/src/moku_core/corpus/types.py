"""Corpus loading types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

CorpusSource = Literal["sample", "wiki40b", "opensubtitles2024"]


@dataclass(frozen=True)
class CorpusLoadConfig:
    source: CorpusSource
    language: str = "en"
    split: str = "train"
    max_documents: int | None = None
    max_sentences: int | None = None
    min_sentence_tokens: int = 6
    max_sentence_tokens: int = 32
    opensubtitles_language_pairs: tuple[str, ...] = ()


@dataclass(frozen=True)
class CorpusSentence:
    source: str
    language: str
    text: str
    tokens: tuple[str, ...]
    content_tokens: tuple[str, ...]
    source_metadata: dict[str, object] = field(default_factory=dict)

    @property
    def token_count(self) -> int:
        return len(self.tokens)
