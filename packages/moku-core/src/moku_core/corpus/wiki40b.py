"""Wiki40B corpus loader."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from moku_core.corpus.types import CorpusLoadConfig, CorpusSentence
from moku_core.corpus.utils import sentence_record
from moku_core.exceptions import CorpusLoadError, OptionalDependencyError
from moku_core.text.cleaning import clean_wiki40b_text
from moku_core.text.sentence_splitters import acceptable_sentence, split_sentences

WIKI40B_DATASET_NAME = "google/wiki40b"


def _default_load_dataset() -> Callable[..., Any]:
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise OptionalDependencyError(
            "Wiki40B loading requires the optional dependency group `moku-core[corpus-hf]`."
        ) from exc
    return load_dataset


def iter_wiki40b_sentences(
    config: CorpusLoadConfig,
    load_dataset_func: Callable[..., Any] | None = None,
) -> Iterator[CorpusSentence]:
    load_dataset_func = load_dataset_func or _default_load_dataset()
    try:
        dataset = load_dataset_func(
            WIKI40B_DATASET_NAME,
            config.language,
            split=config.split,
            streaming=True,
        )
        iterator = dataset
        if config.max_documents is not None:
            iterator = dataset.take(config.max_documents)
    except Exception as exc:
        raise CorpusLoadError(f"Could not open Wiki40B: {type(exc).__name__}: {exc}") from exc

    sentence_count = 0
    for document_index, row in enumerate(iterator):
        text = clean_wiki40b_text(row.get("text", ""))
        for sentence_index, sentence in enumerate(split_sentences(text)):
            if acceptable_sentence(
                sentence,
                language=config.language,
                min_tokens=config.min_sentence_tokens,
                max_tokens=config.max_sentence_tokens,
            ):
                yield sentence_record(
                    text=sentence,
                    source="wiki40b",
                    language=config.language,
                    metadata={
                        "dataset": WIKI40B_DATASET_NAME,
                        "split": config.split,
                        "document_index": document_index,
                        "sentence_index": sentence_index,
                    },
                )
                sentence_count += 1
                if (
                    config.max_sentences is not None
                    and sentence_count >= config.max_sentences
                ):
                    return
