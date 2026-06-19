from __future__ import annotations

from moku_core.corpus import CorpusLoadConfig, iter_corpus_sentences
from moku_core.corpus.opensubtitles2024 import iter_opensubtitles2024_sentences


class FakeDataset:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def __iter__(self):
        return iter(self.rows)

    def take(self, count: int):
        return self.rows[:count]


class NoTakeDataset(FakeDataset):
    def take(self, count: int):
        raise AssertionError("unbounded imports should iterate without calling take")


def test_corpus_load_config_defaults_to_unbounded_imports() -> None:
    config = CorpusLoadConfig(source="sample")

    assert config.max_documents is None
    assert config.max_sentences is None


def test_sample_loader_is_explicit() -> None:
    records = list(
        iter_corpus_sentences(CorpusLoadConfig(source="sample", language="en", max_sentences=2))
    )
    assert len(records) == 2
    assert records[0].source == "sample"
    assert records[0].tokens
    assert records[0].content_tokens


def test_wiki40b_loader_uses_real_cleaning_and_splitting_with_mocked_dataset() -> None:
    def fake_load_dataset(*args, **kwargs) -> FakeDataset:
        assert args[:2] == ("google/wiki40b", "en")
        assert kwargs["streaming"] is True
        return FakeDataset(
            [
                {
                    "text": (
                        "_START_SECTION_ History _END_SECTION_ "
                        "The city built a railway station. "
                        "Workers opened a library near the river."
                    )
                }
            ]
        )

    records = list(
        iter_corpus_sentences(
            CorpusLoadConfig(
                source="wiki40b",
                language="en",
                max_documents=1,
                max_sentences=10,
                min_sentence_tokens=5,
            ),
            load_dataset_func=fake_load_dataset,
        )
    )
    assert [record.text for record in records] == [
        "The city built a railway station.",
        "Workers opened a library near the river.",
    ]


def test_wiki40b_loader_allows_unbounded_documents_and_sentences_by_default() -> None:
    def fake_load_dataset(*args, **kwargs) -> NoTakeDataset:
        assert kwargs["streaming"] is True
        return NoTakeDataset(
            [
                {"text": "The city built a railway station near the river."},
                {"text": "Workers opened a library beside the old market."},
            ]
        )

    records = list(
        iter_corpus_sentences(
            CorpusLoadConfig(source="wiki40b", language="en", min_sentence_tokens=3),
            load_dataset_func=fake_load_dataset,
        )
    )

    assert [record.text for record in records] == [
        "The city built a railway station near the river.",
        "Workers opened a library beside the old market.",
    ]


def test_opensubtitles_loader_extracts_matching_language_with_mocked_dataset() -> None:
    def fake_load_dataset(*args, **kwargs) -> FakeDataset:
        assert args == ("parquet",)
        assert kwargs["streaming"] is True
        return FakeDataset(
            [
                {
                    "src_lang": "en",
                    "src_text": r"{\an8}The museum opened tonight. Visitors waited outside.",
                    "tgt_lang": "es",
                    "tgt_text": "ignored",
                }
            ]
        )

    records = list(
        iter_corpus_sentences(
            CorpusLoadConfig(
                source="opensubtitles2024",
                language="en",
                split="dev",
                max_documents=1,
                min_sentence_tokens=3,
                opensubtitles_language_pairs=("en-es",),
            ),
            load_dataset_func=fake_load_dataset,
        )
    )
    assert [record.text for record in records] == [
        "The museum opened tonight.",
        "Visitors waited outside.",
    ]


def test_opensubtitles_loader_allows_unbounded_documents_and_sentences_by_default() -> None:
    def fake_load_dataset(*args, **kwargs) -> NoTakeDataset:
        assert args == ("parquet",)
        assert kwargs["streaming"] is True
        return NoTakeDataset(
            [
                {
                    "src_lang": "en",
                    "src_text": "The museum opened tonight. Visitors waited outside.",
                    "tgt_lang": "es",
                    "tgt_text": "ignored",
                },
                {
                    "src_lang": "fr",
                    "src_text": "ignored",
                    "tgt_lang": "en",
                    "tgt_text": "Workers repaired the bridge. The station opened early.",
                },
            ]
        )

    records = list(
        iter_corpus_sentences(
            CorpusLoadConfig(
                source="opensubtitles2024",
                language="en",
                split="dev",
                min_sentence_tokens=3,
                opensubtitles_language_pairs=("en-es",),
            ),
            load_dataset_func=fake_load_dataset,
        )
    )

    assert [record.text for record in records] == [
        "The museum opened tonight.",
        "Visitors waited outside.",
        "Workers repaired the bridge.",
        "The station opened early.",
    ]


def test_opensubtitles_loader_discovers_all_pairs_for_language() -> None:
    def fake_list_repo_tree(*args, **kwargs):
        assert args == ("Helsinki-NLP/OpenSubtitles2024",)
        assert kwargs == {"path_in_repo": "dev", "repo_type": "dataset"}
        return [
            {"path": "dev/en-es"},
            {"path": "dev/en-zh_CN"},
            {"path": "dev/fr-zh_CN"},
            {"path": "dev/zh_CN-ja"},
        ]

    def fake_load_dataset(*args, **kwargs) -> FakeDataset:
        assert args == ("parquet",)
        assert kwargs["data_files"] == {
            "dev": [
                "hf://datasets/Helsinki-NLP/OpenSubtitles2024/dev/en-zh_CN/en-zh_CN.parquet",
                "hf://datasets/Helsinki-NLP/OpenSubtitles2024/dev/fr-zh_CN/fr-zh_CN.parquet",
                "hf://datasets/Helsinki-NLP/OpenSubtitles2024/dev/zh_CN-ja/zh_CN-ja.parquet",
            ]
        }
        assert kwargs["split"] == "dev"
        assert kwargs["streaming"] is True
        return FakeDataset([])

    records = list(
        iter_opensubtitles2024_sentences(
            CorpusLoadConfig(
                source="opensubtitles2024",
                language="zh_CN",
                split="dev",
                max_documents=1,
            ),
            load_dataset_func=fake_load_dataset,
            list_repo_tree_func=fake_list_repo_tree,
        )
    )

    assert records == []


def test_opensubtitles_loader_skips_discovery_when_pairs_are_configured() -> None:
    def fake_list_repo_tree(*args, **kwargs):
        raise AssertionError("configured pairs should not require discovery")

    def fake_load_dataset(*args, **kwargs) -> FakeDataset:
        assert kwargs["data_files"] == {
            "dev": [
                "hf://datasets/Helsinki-NLP/OpenSubtitles2024/dev/en-zh_CN/en-zh_CN.parquet"
            ]
        }
        return FakeDataset([])

    records = list(
        iter_opensubtitles2024_sentences(
            CorpusLoadConfig(
                source="opensubtitles2024",
                language="zh_CN",
                split="dev",
                max_documents=1,
                opensubtitles_language_pairs=("en-zh_CN",),
            ),
            load_dataset_func=fake_load_dataset,
            list_repo_tree_func=fake_list_repo_tree,
        )
    )

    assert records == []
