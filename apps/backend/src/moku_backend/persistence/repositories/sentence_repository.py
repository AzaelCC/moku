"""Sentence and corpus persistence."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from uuid import UUID

from moku_core.corpus import CorpusSentence
from moku_core.indexing import BM25Document
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from moku_backend.persistence.models import Corpus, Sentence


class SentenceRepository:
    _TEXT_LOOKUP_BATCH_SIZE = 1_000

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create_corpus(self, *, name: str, source: str, language: str) -> Corpus:
        result = await self.session.execute(select(Corpus).where(Corpus.name == name))
        corpus = result.scalar_one_or_none()
        if corpus is not None:
            corpus.source = source
            corpus.language = language
            await self.session.flush()
            return corpus

        corpus = Corpus(name=name, source=source, language=language)
        self.session.add(corpus)
        await self.session.flush()
        return corpus

    async def get_corpus_by_name(self, name: str) -> Corpus | None:
        result = await self.session.execute(select(Corpus).where(Corpus.name == name))
        return result.scalar_one_or_none()

    async def get_corpus_by_public_id(self, public_id: UUID) -> Corpus | None:
        result = await self.session.execute(select(Corpus).where(Corpus.public_id == public_id))
        return result.scalar_one_or_none()

    async def get_latest_corpus(self) -> Corpus | None:
        result = await self.session.execute(
            select(Corpus).order_by(Corpus.created_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def replace_sentences(
        self,
        *,
        corpus: Corpus,
        sentences: Sequence[CorpusSentence],
    ) -> list[CorpusSentence]:
        await self.session.execute(delete(Sentence).where(Sentence.corpus_id == corpus.id))
        unique_sentences = self._deduplicate_by_text(sentences)
        existing_texts = await self.existing_texts(sentence.text for sentence in unique_sentences)
        new_sentences = [
            sentence for sentence in unique_sentences if sentence.text not in existing_texts
        ]
        self.session.add_all(
            [
                Sentence(
                    corpus_id=corpus.id,
                    source=sentence.source,
                    language=sentence.language,
                    text=sentence.text,
                    tokens=list(sentence.tokens),
                    content_tokens=list(sentence.content_tokens),
                    token_count=sentence.token_count,
                    source_metadata=sentence.source_metadata,
                )
                for sentence in new_sentences
            ]
        )
        await self.session.flush()
        return new_sentences

    async def existing_texts(self, texts: Iterable[str]) -> set[str]:
        unique_texts = list(dict.fromkeys(texts))
        existing: set[str] = set()
        for start in range(0, len(unique_texts), self._TEXT_LOOKUP_BATCH_SIZE):
            batch = unique_texts[start : start + self._TEXT_LOOKUP_BATCH_SIZE]
            result = await self.session.execute(
                select(Sentence.text).where(Sentence.text.in_(batch))
            )
            existing.update(result.scalars().all())
        return existing

    def _deduplicate_by_text(
        self, sentences: Sequence[CorpusSentence]
    ) -> list[CorpusSentence]:
        seen_texts: set[str] = set()
        deduplicated: list[CorpusSentence] = []
        for sentence in sentences:
            if sentence.text in seen_texts:
                continue
            seen_texts.add(sentence.text)
            deduplicated.append(sentence)
        return deduplicated

    async def list_documents(self, corpus: Corpus, limit: int | None = None) -> list[BM25Document]:
        statement = select(Sentence).where(Sentence.corpus_id == corpus.id).order_by(Sentence.id)
        if limit is not None:
            statement = statement.limit(limit)
        result = await self.session.execute(statement)
        sentences = result.scalars().all()
        return [
            BM25Document(
                identifier=str(sentence.public_id),
                text=sentence.text,
                content_tokens=tuple(sentence.content_tokens),
            )
            for sentence in sentences
        ]
