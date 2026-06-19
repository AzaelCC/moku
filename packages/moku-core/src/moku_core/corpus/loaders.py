"""Corpus loader dispatch."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import Any

from moku_core.corpus.opensubtitles2024 import iter_opensubtitles2024_sentences
from moku_core.corpus.sample import iter_sample_sentences
from moku_core.corpus.types import CorpusLoadConfig, CorpusSentence
from moku_core.corpus.wiki40b import iter_wiki40b_sentences


def iter_corpus_sentences(
    config: CorpusLoadConfig,
    load_dataset_func: Callable[..., Any] | None = None,
    list_repo_tree_func: Callable[..., Iterable[Any]] | None = None,
) -> Iterator[CorpusSentence]:
    if config.source == "sample":
        yield from iter_sample_sentences(config)
        return
    if config.source == "wiki40b":
        yield from iter_wiki40b_sentences(config, load_dataset_func=load_dataset_func)
        return
    if config.source == "opensubtitles2024":
        yield from iter_opensubtitles2024_sentences(
            config,
            load_dataset_func=load_dataset_func,
            list_repo_tree_func=list_repo_tree_func,
        )
        return
    raise ValueError(f"Unsupported corpus source: {config.source!r}")
