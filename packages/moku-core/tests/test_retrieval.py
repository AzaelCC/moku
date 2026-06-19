from __future__ import annotations

from moku_core.indexing import BM25Document, build_bm25_index, weighted_bm25_scores
from moku_core.retrieval import ScheduleItem, retrieve_recommendations, scheduling_word_penalty
from moku_core.retrieval.recommendations import filter_documents_by_top_k_allowed_words
from moku_core.retrieval.scoring import due_query_terms


def test_weighted_bm25_scores_due_words() -> None:
    documents = [
        BM25Document("1", "The archive opened.", ("the", "archive", "opened")),
        BM25Document("2", "The market closed.", ("the", "market", "closed")),
    ]
    index = build_bm25_index(documents)
    scores = weighted_bm25_scores(index, due_query_terms([ScheduleItem("archive", 0, 7)]))
    assert scores[0] > scores[1]


def test_scheduling_penalty_clamps_overdue_and_future_words() -> None:
    schedule = {"archive": ScheduleItem("archive", -2, 7), "market": ScheduleItem("market", 3, 6)}
    assert scheduling_word_penalty("archive", schedule) == 0
    assert scheduling_word_penalty("market", schedule) == 0.5
    assert scheduling_word_penalty("irrigation", schedule, {"irrigation"}) == 0
    assert scheduling_word_penalty("unknown", schedule) == 1


def test_recommendations_rerank_candidate_pool_by_scheduling_score() -> None:
    documents = [
        BM25Document("1", "The archive opened near the river.", ("archive", "opened", "river")),
        BM25Document(
            "2",
            "The archive and irrigation report changed.",
            ("archive", "irrigation", "report", "changed"),
        ),
    ]
    recommendations = retrieve_recommendations(
        documents=documents,
        schedule=[ScheduleItem("archive", 0, 7)],
        requested_new_words=("irrigation",),
        result_limit=2,
    )
    assert recommendations
    assert recommendations[0].document_id == "2"
    assert recommendations[0].requested_new_words == ("irrigation",)


def test_filter_documents_by_top_k_allowed_words_keeps_simple_vocabulary() -> None:
    documents = [
        BM25Document("1", "Common phrase.", ("common", "phrase")),
        BM25Document("2", "Common rare.", ("common", "rare")),
        BM25Document("3", "Common common.", ("common", "common")),
    ]

    filtered = filter_documents_by_top_k_allowed_words(documents, top_k_allowed_words=2)

    assert [document.identifier for document in filtered] == ["1", "3"]


def test_recommendations_apply_top_k_allowed_words_before_bm25() -> None:
    documents = [
        BM25Document("1", "Archive common.", ("archive", "common")),
        BM25Document("2", "Archive rare.", ("archive", "rare")),
        BM25Document("3", "Archive common common.", ("archive", "common", "common")),
    ]
    schedule = [ScheduleItem("archive", 0, 7)]

    filtered = retrieve_recommendations(
        documents=documents,
        schedule=schedule,
        result_limit=5,
        candidate_count=5,
        top_k_allowed_words=2,
    )
    unfiltered = retrieve_recommendations(
        documents=documents,
        schedule=schedule,
        result_limit=5,
        candidate_count=5,
        top_k_allowed_words=0,
    )

    assert [recommendation.document_id for recommendation in filtered] == ["1", "3"]
    assert [recommendation.document_id for recommendation in unfiltered] == ["1", "2", "3"]
