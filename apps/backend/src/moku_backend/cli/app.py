"""Typer CLI entrypoint."""

from __future__ import annotations

import asyncio
from typing import Annotated

import click
import typer

from moku_backend.config import Settings
from moku_backend.db.engine import create_engine, create_sessionmaker
from moku_backend.services.anki_connect_client import AnkiConnectError
from moku_backend.services.anki_import_service import AnkiImportError, AnkiImportService
from moku_backend.services.anki_package_import_service import (
    AnkiPackageImportError,
    AnkiPackageImportService,
)
from moku_backend.services.corpus_import_service import CorpusImportService

app = typer.Typer(no_args_is_help=True)


@app.callback()
def callback() -> None:
    """Moku backend management commands."""


@app.command("import-corpus")
def import_corpus(
    source: Annotated[
        str,
        typer.Option(help="Corpus source: sample, wiki40b, or opensubtitles2024."),
    ] = "sample",
    language: Annotated[str, typer.Option(help="Language tag to import.")] = "en",
    corpus_name: Annotated[str | None, typer.Option(help="Persisted corpus name.")] = None,
    max_documents: Annotated[
        int | None,
        typer.Option(help="Maximum source documents/segments to scan. Omit for no limit."),
    ] = None,
    max_sentences: Annotated[
        int | None,
        typer.Option(help="Maximum accepted sentences to persist. Omit for no limit."),
    ] = None,
    split: Annotated[str, typer.Option(help="Dataset split for real corpus loaders.")] = "dev",
    opensubtitles_language_pairs: Annotated[
        str | None,
        typer.Option(
            help=(
                "Comma-separated OpenSubtitles language pairs, e.g. en-zh_CN. "
                "Omit to use all pairs containing --language."
            )
        ),
    ] = None,
    seed_default_learner: Annotated[
        bool | None,
        typer.Option(
            "--seed-default-learner/--no-seed-default-learner",
            help="Seed demo learner cards. Defaults to true for sample imports only.",
        ),
    ] = None,
) -> None:
    result = asyncio.run(
        _import_corpus(
            source=source,
            language=language,
            corpus_name=corpus_name,
            max_documents=max_documents,
            max_sentences=max_sentences,
            split=split,
            opensubtitles_language_pairs=_split_pairs(opensubtitles_language_pairs),
            seed_default_learner=seed_default_learner,
        )
    )
    typer.echo(
        "Imported "
        f"{result.sentence_count} sentences into {result.corpus_name} "
        f"(run={result.run_public_id}, corpus={result.corpus_public_id}, "
        f"seeded_learner_cards={result.seeded_learner_cards})."
    )


@app.command("import-anki")
def import_anki(
    deck: Annotated[str, typer.Option(help="Anki deck name to import, including subdecks.")] = ...,
    word_field: Annotated[
        str,
        typer.Option(help="Required Anki note field to import as the learner word."),
    ] = ...,
    language: Annotated[str | None, typer.Option(help="Moku language tag.")] = None,
    learner_handle: Annotated[
        str | None,
        typer.Option(help="Moku learner handle to replace for this language."),
    ] = None,
) -> None:
    try:
        result = asyncio.run(
            _import_anki(
                deck=deck,
                word_field=word_field,
                language=language,
                learner_handle=learner_handle,
            )
        )
    except (AnkiConnectError, AnkiImportError) as exc:
        raise click.ClickException(str(exc)) from exc

    typer.echo(
        "Imported "
        f"{result.imported_card_count} learner cards from Anki deck {result.deck} "
        f"for {result.learner_handle} ({result.language}; found={result.found_card_count}, "
        f"scheduled={result.scheduled_count}, unscheduled={result.unscheduled_count}, "
        f"suspended={result.suspended_count}, skipped={result.skipped_count}, "
        f"duplicates={result.duplicate_card_count})."
    )
    if result.skipped_samples:
        samples = ", ".join(
            f"{sample.card_id}:{sample.reason}" for sample in result.skipped_samples
        )
        typer.echo(f"Skipped sample cards: {samples}")


@app.command("import-anki-package")
def import_anki_package(
    package_path: Annotated[
        str,
        typer.Option(help="Path to an Anki .apkg or .colpkg export."),
    ] = ...,
    deck: Annotated[
        str,
        typer.Option(help="Anki deck name to import, including subdecks."),
    ] = ...,
    word_field: Annotated[
        str,
        typer.Option(help="Required Anki note field to import as the learner word."),
    ] = ...,
    language: Annotated[str | None, typer.Option(help="Moku language tag.")] = None,
    learner_handle: Annotated[
        str | None,
        typer.Option(help="Moku learner handle to replace for this language."),
    ] = None,
) -> None:
    try:
        result = asyncio.run(
            _import_anki_package(
                package_path=package_path,
                deck=deck,
                word_field=word_field,
                language=language,
                learner_handle=learner_handle,
            )
        )
    except AnkiPackageImportError as exc:
        raise click.ClickException(str(exc)) from exc

    typer.echo(
        "Imported "
        f"{result.imported_card_count} learner cards from Anki package deck {result.deck} "
        f"for {result.learner_handle} ({result.language}; found={result.found_card_count}, "
        f"scheduled={result.scheduled_count}, unscheduled={result.unscheduled_count}, "
        f"suspended={result.suspended_count}, skipped={result.skipped_count}, "
        f"duplicates={result.duplicate_card_count}, review_logs="
        f"{result.imported_review_log_count}, fsrs_cards={result.fsrs_card_count})."
    )
    if result.skipped_samples:
        samples = ", ".join(
            f"{sample.card_id}:{sample.reason}" for sample in result.skipped_samples
        )
        typer.echo(f"Skipped sample cards: {samples}")


async def _import_corpus(
    *,
    source: str,
    language: str,
    corpus_name: str | None,
    max_documents: int | None,
    max_sentences: int | None,
    split: str,
    opensubtitles_language_pairs: tuple[str, ...],
    seed_default_learner: bool | None,
):
    settings = Settings()
    engine = create_engine(settings)
    sessionmaker = create_sessionmaker(engine)
    try:
        async with sessionmaker() as session:
            service = CorpusImportService(session, settings)
            return await service.import_corpus(
                source=source,
                language=language,
                corpus_name=corpus_name,
                max_documents=max_documents,
                max_sentences=max_sentences,
                split=split,
                opensubtitles_language_pairs=opensubtitles_language_pairs,
                seed_default_learner=seed_default_learner,
            )
    finally:
        await engine.dispose()


async def _import_anki(
    *,
    deck: str,
    word_field: str,
    language: str | None,
    learner_handle: str | None,
):
    settings = Settings()
    engine = create_engine(settings)
    sessionmaker = create_sessionmaker(engine)
    try:
        async with sessionmaker() as session:
            service = AnkiImportService(session, settings)
            return await service.import_deck(
                deck=deck,
                word_field=word_field,
                language=language,
                learner_handle=learner_handle,
            )
    finally:
        await engine.dispose()


async def _import_anki_package(
    *,
    package_path: str,
    deck: str,
    word_field: str,
    language: str | None,
    learner_handle: str | None,
):
    settings = Settings()
    engine = create_engine(settings)
    sessionmaker = create_sessionmaker(engine)
    try:
        async with sessionmaker() as session:
            service = AnkiPackageImportService(session, settings)
            return await service.import_package(
                package_path=package_path,
                deck=deck,
                word_field=word_field,
                language=language,
                learner_handle=learner_handle,
            )
    finally:
        await engine.dispose()


def _split_pairs(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(pair.strip() for pair in value.split(",") if pair.strip())


def main() -> None:
    app()
