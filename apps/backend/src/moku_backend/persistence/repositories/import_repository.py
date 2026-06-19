"""Import run persistence."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from moku_backend.persistence.models import ImportRun


class ImportRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_run(
        self,
        *,
        source: str,
        language: str,
        corpus_name: str,
        max_documents: int | None,
        max_sentences: int | None,
        metadata: dict[str, object] | None = None,
    ) -> ImportRun:
        run = ImportRun(
            source=source,
            language=language,
            corpus_name=corpus_name,
            status="running",
            max_documents=max_documents,
            max_sentences=max_sentences,
            run_metadata=metadata or {},
        )
        self.session.add(run)
        await self.session.flush()
        return run

    async def mark_succeeded(self, run_id: int, sentence_count: int) -> ImportRun:
        run = await self._get(run_id)
        run.status = "succeeded"
        run.sentence_count = sentence_count
        run.finished_at = datetime.now(UTC)
        await self.session.flush()
        return run

    async def mark_failed(self, run_id: int, error_message: str) -> ImportRun:
        run = await self._get(run_id)
        run.status = "failed"
        run.error_message = error_message
        run.finished_at = datetime.now(UTC)
        await self.session.flush()
        return run

    async def _get(self, run_id: int) -> ImportRun:
        result = await self.session.execute(select(ImportRun).where(ImportRun.id == run_id))
        run = result.scalar_one_or_none()
        if run is None:
            raise LookupError(f"Import run not found: {run_id}")
        return run
