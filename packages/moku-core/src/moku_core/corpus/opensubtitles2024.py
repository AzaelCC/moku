"""OpenSubtitles2024 corpus loader."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import Any

from moku_core.corpus.types import CorpusLoadConfig, CorpusSentence
from moku_core.corpus.utils import parse_language_pairs, sentence_record
from moku_core.exceptions import CorpusLoadError, OptionalDependencyError
from moku_core.text.sentence_splitters import acceptable_sentence, split_sentences

OPENSUBTITLES_DATASET_NAME = "Helsinki-NLP/OpenSubtitles2024"


def _default_load_dataset() -> Callable[..., Any]:
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise OptionalDependencyError(
            "OpenSubtitles2024 loading requires `moku-core[corpus-hf]`."
        ) from exc
    return load_dataset


def _default_list_repo_tree() -> Callable[..., Iterable[Any]]:
    try:
        from huggingface_hub import list_repo_tree
    except ImportError as exc:
        raise OptionalDependencyError(
            "OpenSubtitles2024 loading requires `moku-core[corpus-hf]`."
        ) from exc
    return list_repo_tree


def _repo_tree_entry_path(entry: Any) -> str | None:
    path = getattr(entry, "path", None)
    if path is None and isinstance(entry, dict):
        path = entry.get("path")
    return path if isinstance(path, str) else None


def _pair_from_repo_tree_entry(entry: Any, split: str) -> str | None:
    path = _repo_tree_entry_path(entry)
    if not path:
        return None

    normalized_path = path.strip("/")
    normalized_split = split.strip("/")
    prefix = f"{normalized_split}/"
    if normalized_path.startswith(prefix):
        normalized_path = normalized_path[len(prefix) :]

    pair = normalized_path.split("/", maxsplit=1)[0]
    return pair if "-" in pair else None


def _pair_contains_language(pair: str, language: str) -> bool:
    return language in pair.split("-")


def _discover_language_pairs(
    *,
    language: str,
    split: str,
    list_repo_tree_func: Callable[..., Iterable[Any]],
) -> tuple[str, ...]:
    try:
        entries = list_repo_tree_func(
            OPENSUBTITLES_DATASET_NAME,
            path_in_repo=split,
            repo_type="dataset",
        )
        pairs = {
            pair
            for entry in entries
            if (pair := _pair_from_repo_tree_entry(entry, split))
            and _pair_contains_language(pair, language)
        }
    except Exception as exc:
        raise CorpusLoadError(
            "Could not list OpenSubtitles2024 language pairs "
            f"for split {split!r}: {type(exc).__name__}: {exc}"
        ) from exc

    if not pairs:
        raise CorpusLoadError(
            f"No OpenSubtitles2024 language pairs found for {language!r} in split {split!r}."
        )
    return tuple(sorted(pairs))


def _default_language_pairs(
    language: str,
    split: str,
    configured_pairs: tuple[str, ...],
    list_repo_tree_func: Callable[..., Iterable[Any]] | None,
) -> tuple[str, ...]:
    pairs = parse_language_pairs(configured_pairs)
    if pairs:
        return pairs
    return _discover_language_pairs(
        language=language,
        split=split,
        list_repo_tree_func=list_repo_tree_func or _default_list_repo_tree(),
    )


def iter_opensubtitles2024_sentences(
    config: CorpusLoadConfig,
    load_dataset_func: Callable[..., Any] | None = None,
    list_repo_tree_func: Callable[..., Iterable[Any]] | None = None,
) -> Iterator[CorpusSentence]:
    load_dataset_func = load_dataset_func or _default_load_dataset()
    pairs = _default_language_pairs(
        config.language,
        config.split,
        config.opensubtitles_language_pairs,
        list_repo_tree_func,
    )
    data_files = {
        config.split: [
            f"hf://datasets/{OPENSUBTITLES_DATASET_NAME}/{config.split}/{pair}/{pair}.parquet"
            for pair in pairs
        ]
    }

    try:
        dataset = load_dataset_func(
            "parquet",
            data_files=data_files,
            split=config.split,
            streaming=True,
        )
        iterator = dataset
        if config.max_documents is not None:
            iterator = dataset.take(config.max_documents)
    except Exception as exc:
        raise CorpusLoadError(
            f"Could not open OpenSubtitles2024: {type(exc).__name__}: {exc}"
        ) from exc

    sentence_count = 0
    for segment_index, row in enumerate(iterator):
        texts = []
        if row.get("src_lang") == config.language:
            texts.append(("src_text", row.get("src_text", "")))
        if row.get("tgt_lang") == config.language:
            texts.append(("tgt_text", row.get("tgt_text", "")))

        for field_name, text in texts:
            for sentence_index, sentence in enumerate(split_sentences(text)):
                if acceptable_sentence(
                    sentence,
                    language=config.language,
                    min_tokens=config.min_sentence_tokens,
                    max_tokens=config.max_sentence_tokens,
                ):
                    yield sentence_record(
                        text=sentence,
                        source="opensubtitles2024",
                        language=config.language,
                        metadata={
                            "dataset": OPENSUBTITLES_DATASET_NAME,
                            "split": config.split,
                            "language_pairs": list(pairs),
                            "segment_index": segment_index,
                            "field": field_name,
                            "sentence_index": sentence_index,
                        },
                    )
                    sentence_count += 1
                    if (
                        config.max_sentences is not None
                        and sentence_count >= config.max_sentences
                    ):
                        return
