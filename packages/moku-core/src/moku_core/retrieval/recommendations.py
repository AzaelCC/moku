"""End-to-end candidate retrieval and reranking."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from moku_core.indexing.bm25 import build_bm25_index, weighted_bm25_scores
from moku_core.indexing.types import BM25Document
from moku_core.retrieval.scoring import ScheduleItem, due_query_terms, scheduling_score


@dataclass(frozen=True)
class Recommendation:
    document_id: str
    sentence: str
    bm25_rank: int
    bm25_score: float
    scheduling_score: float
    known_words: tuple[str, ...]
    due_words: tuple[str, ...]
    early_words: tuple[str, ...]
    requested_new_words: tuple[str, ...]
    unrequested_new_words: tuple[str, ...]


def retrieve_recommendations(
    documents: Sequence[BM25Document],
    schedule: Sequence[ScheduleItem],
    requested_new_words: Iterable[str] = (),
    result_limit: int = 10,
    candidate_count: int = 25,
    horizon_days: int = 14,
    top_k_allowed_words: int = 0,
) -> list[Recommendation]:
    documents = filter_documents_by_top_k_allowed_words(documents, top_k_allowed_words)
    query_terms = due_query_terms(
        schedule=schedule,
        requested_new_words=requested_new_words,
        horizon_days=horizon_days,
    )
    if not documents or not query_terms:
        return []

    requested_new_word_tuple = tuple(requested_new_words)
    index = build_bm25_index(documents)
    scores = weighted_bm25_scores(index, query_terms)
    ranked_document_ids = sorted(
        range(len(scores)), key=lambda index_id: scores[index_id], reverse=True
    )
    ranked_document_ids = [
        document_id for document_id in ranked_document_ids if scores[document_id] > 0
    ][:candidate_count]

    candidates = []
    for bm25_rank, document_id in enumerate(ranked_document_ids, start=1):
        document = documents[document_id]
        details = scheduling_score(
            document.content_tokens,
            schedule=schedule,
            requested_new_words=requested_new_word_tuple,
        )
        candidates.append(
            Recommendation(
                document_id=document.identifier,
                sentence=document.text,
                bm25_rank=bm25_rank,
                bm25_score=float(scores[document_id]),
                scheduling_score=details.scheduling_score,
                known_words=details.known_words,
                due_words=details.due_words,
                early_words=details.early_words,
                requested_new_words=details.requested_new_words,
                unrequested_new_words=details.unrequested_new_words,
            )
        )

    return sorted(
        candidates,
        key=lambda candidate: (candidate.scheduling_score, candidate.bm25_rank),
    )[:result_limit]


def filter_documents_by_top_k_allowed_words(
    documents: Sequence[BM25Document], top_k_allowed_words: int
) -> list[BM25Document]:
    if top_k_allowed_words <= 0:
        return list(documents)

    counts: Counter[str] = Counter()
    for document in documents:
        counts.update(document.content_tokens)

    allowed_words = {
        word for word, _count in counts.most_common(top_k_allowed_words)
    }
    return [
        document
        for document in documents
        if set(document.content_tokens).issubset(allowed_words)
    ]
