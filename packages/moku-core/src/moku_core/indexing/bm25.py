"""Weighted BM25 scoring."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence

from moku_core.indexing.types import BM25Document, BM25Index, WeightedQueryTerm


def build_bm25_index(documents: Sequence[BM25Document]) -> BM25Index:
    term_frequencies = tuple(Counter(document.content_tokens) for document in documents)
    document_frequencies: Counter[str] = Counter()
    for term_frequency in term_frequencies:
        document_frequencies.update(term_frequency.keys())

    document_count = len(documents)
    idf = {
        term: math.log(1 + (document_count - frequency + 0.5) / (frequency + 0.5))
        for term, frequency in document_frequencies.items()
    }
    document_lengths = tuple(
        float(sum(term_frequency.values())) for term_frequency in term_frequencies
    )
    average_document_length = (
        sum(document_lengths) / len(document_lengths) if document_lengths else 1.0
    )
    return BM25Index(
        documents=tuple(documents),
        term_frequencies=term_frequencies,
        document_frequencies=document_frequencies,
        idf=idf,
        document_lengths=document_lengths,
        average_document_length=average_document_length,
    )


def weighted_bm25_scores(
    index: BM25Index,
    query_terms: Sequence[WeightedQueryTerm],
    k1: float = 1.5,
    b: float = 0.75,
) -> list[float]:
    scores = [0.0 for _document in index.documents]
    average_length = index.average_document_length or 1.0

    for query_term in query_terms:
        idf = index.idf.get(query_term.word)
        if idf is None:
            continue

        days_factor = max(query_term.days_until_due, 0) + 1
        for document_id, term_frequency in enumerate(index.term_frequencies):
            frequency = term_frequency.get(query_term.word, 0)
            if frequency == 0:
                continue
            length_norm = 1 - b + b * (index.document_lengths[document_id] / average_length)
            denominator = frequency + k1 * length_norm * days_factor
            scores[document_id] += query_term.weight * idf * ((k1 + 1) * frequency) / denominator

    return scores
