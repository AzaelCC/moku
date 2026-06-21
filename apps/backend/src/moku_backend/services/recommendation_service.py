"""Recommendation orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from moku_core.retrieval import Recommendation, retrieve_recommendations
from sqlalchemy.ext.asyncio import AsyncSession

from moku_backend.config import Settings
from moku_backend.persistence.models import Corpus, Learner
from moku_backend.persistence.repositories.learner_repository import LearnerRepository
from moku_backend.persistence.repositories.sentence_repository import SentenceRepository


@dataclass(frozen=True)
class RecommendationResult:
    corpus: Corpus
    learner: Learner
    recommendations: list[Recommendation]


class RecommendationService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.learners = LearnerRepository(session)
        self.sentences = SentenceRepository(session)

    async def recommend(
        self,
        *,
        corpus_name: str | None = None,
        corpus_public_id: UUID | None = None,
        learner_public_id: UUID | None = None,
        requested_new_words: tuple[str, ...] = (),
        top_k: int = 10,
        candidate_count: int = 25,
        horizon_days: int = 14,
        top_k_allowed_words: int = 5_000,
    ) -> RecommendationResult:
        corpus = await self._resolve_corpus(corpus_name=corpus_name, public_id=corpus_public_id)
        learner = await self._resolve_learner(learner_public_id)
        documents = await self.sentences.list_documents(
            corpus, top_k_allowed_words=top_k_allowed_words
        )
        schedule = await self.learners.list_schedule(learner=learner, language=corpus.language)
        recommendations = retrieve_recommendations(
            documents=documents,
            schedule=schedule,
            requested_new_words=requested_new_words,
            result_limit=top_k,
            candidate_count=max(candidate_count, top_k),
            horizon_days=horizon_days,
            top_k_allowed_words=0,
        )
        return RecommendationResult(corpus=corpus, learner=learner, recommendations=recommendations)

    async def _resolve_corpus(self, corpus_name: str | None, public_id: UUID | None) -> Corpus:
        corpus = None
        if public_id is not None:
            corpus = await self.sentences.get_corpus_by_public_id(public_id)
        elif corpus_name is not None:
            corpus = await self.sentences.get_corpus_by_name(corpus_name)
        else:
            corpus = await self.sentences.get_corpus_by_name(self.settings.default_corpus_name)
            if corpus is None:
                corpus = await self.sentences.get_latest_corpus()

        if corpus is None:
            raise LookupError("No corpus has been imported yet.")
        return corpus

    async def _resolve_learner(self, learner_public_id: UUID | None) -> Learner:
        if learner_public_id is not None:
            learner = await self.learners.get_by_public_id(learner_public_id)
            if learner is None:
                raise LookupError(f"Learner not found: {learner_public_id}")
            return learner
        return await self.learners.get_or_create_default(self.settings.default_learner_handle)
