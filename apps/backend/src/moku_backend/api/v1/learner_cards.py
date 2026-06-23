"""Learner card API."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from moku_backend.api.deps import get_session, get_settings
from moku_backend.config import Settings
from moku_backend.persistence.models import LearnerCard
from moku_backend.services.learner_card_service import (
    LearnerCardConflictError,
    LearnerCardNotFoundError,
    LearnerCardReviewResult,
    LearnerCardService,
    LearnerCardValidationError,
)

router = APIRouter(prefix="/learner-cards", tags=["learner-cards"])

ReviewRating = Literal["again", "hard", "good", "easy"]


class FsrsStateSummary(BaseModel):
    card_id: int
    state: str
    step: int | None
    stability: float | None
    difficulty: float | None
    last_review_at: datetime | None


class LearnerCardResponse(BaseModel):
    public_id: UUID
    note_id: UUID
    learner_id: UUID
    word: str
    language: str
    card_type: str
    schedule_status: str
    scheduling_algorithm: str
    due_at: datetime | None
    interval_days: int | None
    fsrs_state: FsrsStateSummary | None = None
    review_log_id: UUID | None = None


class CreateLearnerCardRequest(BaseModel):
    word: str = Field(min_length=1, max_length=255)
    card_type: str = Field(min_length=1, max_length=120)
    language: str | None = Field(default=None, min_length=1, max_length=32)
    learner_id: UUID | None = None


class ReviewLearnerCardRequest(BaseModel):
    rating: ReviewRating
    reviewed_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)


@router.get("", response_model=list[LearnerCardResponse])
async def list_learner_cards(
    *,
    learner_id: UUID | None = None,
    language: str | None = None,
    schedule_status: str | None = None,
    scheduling_algorithm: str | None = None,
    due_before: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[LearnerCardResponse]:
    service = LearnerCardService(session, settings)
    try:
        cards = await service.list_cards(
            learner_public_id=learner_id,
            language=language,
            schedule_status=schedule_status,
            scheduling_algorithm=scheduling_algorithm,
            due_before=due_before,
            limit=limit,
        )
    except LearnerCardNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LearnerCardValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return [_card_response(card) for card in cards]


@router.post("", response_model=LearnerCardResponse, status_code=201)
async def create_learner_card(
    *,
    request: CreateLearnerCardRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LearnerCardResponse:
    service = LearnerCardService(session, settings)
    try:
        card = await service.create_fsrs_card(
            word=request.word,
            card_type=request.card_type,
            language=request.language,
            learner_public_id=request.learner_id,
        )
    except LearnerCardNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LearnerCardConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LearnerCardValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _card_response(card)


@router.post("/{card_public_id}/reviews", response_model=LearnerCardResponse)
async def review_learner_card(
    *,
    card_public_id: UUID,
    request: ReviewLearnerCardRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LearnerCardResponse:
    service = LearnerCardService(session, settings)
    try:
        result = await service.review_card(
            card_public_id=card_public_id,
            rating=request.rating,
            reviewed_at=request.reviewed_at,
            duration_ms=request.duration_ms,
        )
    except LearnerCardNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LearnerCardConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LearnerCardValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _review_response(result)


def _review_response(result: LearnerCardReviewResult) -> LearnerCardResponse:
    return _card_response(result.card, review_log_id=result.review_log.public_id)


def _card_response(
    card: LearnerCard,
    *,
    review_log_id: UUID | None = None,
) -> LearnerCardResponse:
    return LearnerCardResponse(
        public_id=card.public_id,
        note_id=card.note.public_id,
        learner_id=card.note.learner.public_id,
        word=card.note.word,
        language=card.note.language,
        card_type=card.card_type,
        schedule_status=card.schedule_status,
        scheduling_algorithm=card.scheduling_algorithm,
        due_at=card.due_at,
        interval_days=card.interval_days,
        fsrs_state=_fsrs_state(card.fsrs_card),
        review_log_id=review_log_id,
    )


def _fsrs_state(value: dict[str, object] | None) -> FsrsStateSummary | None:
    if value is None:
        return None
    state_value = int(value["state"])
    return FsrsStateSummary(
        card_id=int(value["card_id"]),
        state={1: "learning", 2: "review", 3: "relearning"}.get(state_value, str(state_value)),
        step=value.get("step") if isinstance(value.get("step"), int) else None,
        stability=(
            float(value["stability"]) if isinstance(value.get("stability"), int | float) else None
        ),
        difficulty=(
            float(value["difficulty"]) if isinstance(value.get("difficulty"), int | float) else None
        ),
        last_review_at=(
            datetime.fromisoformat(str(value["last_review"])) if value.get("last_review") else None
        ),
    )
