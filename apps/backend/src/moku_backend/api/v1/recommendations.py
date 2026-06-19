"""Recommendation API."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from moku_backend.api.deps import get_session, get_settings
from moku_backend.config import Settings
from moku_backend.services.recommendation_service import RecommendationService

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


class RecommendationItem(BaseModel):
    sentence_id: UUID
    sentence: str
    bm25_rank: int
    bm25_score: float
    scheduling_score: float
    due_words: list[str]
    early_words: list[str]
    requested_new_words: list[str]
    unrequested_new_words: list[str]


class RecommendationResponse(BaseModel):
    corpus_id: UUID
    corpus_name: str
    learner_id: UUID
    recommendations: list[RecommendationItem] = Field(default_factory=list)


@router.get("", response_model=RecommendationResponse)
async def recommendations(
    *,
    corpus_name: str | None = None,
    corpus_id: UUID | None = None,
    learner_id: UUID | None = None,
    requested_new_words: str | None = Query(
        default=None,
        description="Comma-separated words to treat as requested new vocabulary.",
    ),
    top_k: int = Query(default=10, ge=1, le=50),
    candidate_count: int = Query(default=25, ge=1, le=200),
    horizon_days: int = Query(default=14, ge=0, le=365),
    top_k_allowed_words: int = Query(
        default=5_000,
        ge=0,
        le=1_000_000,
        description=(
            "Keep only sentences whose content tokens are all in the top K corpus "
            "words; 0 disables the filter."
        ),
    ),
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RecommendationResponse:
    service = RecommendationService(session, settings)
    requested_words = _split_words(requested_new_words)
    try:
        result = await service.recommend(
            corpus_name=corpus_name,
            corpus_public_id=corpus_id,
            learner_public_id=learner_id,
            requested_new_words=requested_words,
            top_k=top_k,
            candidate_count=candidate_count,
            horizon_days=horizon_days,
            top_k_allowed_words=top_k_allowed_words,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return RecommendationResponse(
        corpus_id=result.corpus.public_id,
        corpus_name=result.corpus.name,
        learner_id=result.learner.public_id,
        recommendations=[
            RecommendationItem(
                sentence_id=UUID(recommendation.document_id),
                sentence=recommendation.sentence,
                bm25_rank=recommendation.bm25_rank,
                bm25_score=recommendation.bm25_score,
                scheduling_score=recommendation.scheduling_score,
                due_words=list(recommendation.due_words),
                early_words=list(recommendation.early_words),
                requested_new_words=list(recommendation.requested_new_words),
                unrequested_new_words=list(recommendation.unrequested_new_words),
            )
            for recommendation in result.recommendations
        ],
    )


def _split_words(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(word.strip().lower() for word in value.split(",") if word.strip())
