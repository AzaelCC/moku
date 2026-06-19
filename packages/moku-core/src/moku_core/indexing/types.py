"""BM25 types."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class BM25Document:
    identifier: str
    text: str
    content_tokens: tuple[str, ...]


@dataclass(frozen=True)
class WeightedQueryTerm:
    word: str
    days_until_due: int = 0
    weight: float = 1.0


@dataclass(frozen=True)
class BM25Index:
    documents: tuple[BM25Document, ...]
    term_frequencies: tuple[Counter[str], ...]
    document_frequencies: Counter[str]
    idf: dict[str, float]
    document_lengths: tuple[float, ...]
    average_document_length: float
