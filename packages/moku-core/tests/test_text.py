from __future__ import annotations

from moku_core.text import (
    clean_corpus_text,
    clean_wiki40b_text,
    content_tokens,
    is_chinese_language,
    split_sentences,
    tokenize,
    tokenizers,
)


def test_clean_corpus_text_removes_subtitle_markup() -> None:
    assert clean_corpus_text(r"{\an8}Hello \h world") == "Hello world"


def test_clean_wiki40b_text_removes_markers() -> None:
    text = "_START_SECTION_ History _END_SECTION_ A city grew. _NEWLINE_ It changed."
    assert clean_wiki40b_text(text) == "A city grew. It changed."


def test_split_sentences_handles_english_boundaries() -> None:
    assert split_sentences("The river rose. Workers repaired the bridge.") == [
        "The river rose.",
        "Workers repaired the bridge.",
    ]


def test_split_sentences_handles_chinese_punctuation() -> None:
    assert split_sentences("我喜欢中文。我们每天复习。") == ["我喜欢中文。", "我们每天复习。"]


def test_english_tokenization() -> None:
    assert tokenize("The city council approved a long-term plan.", language="en") == [
        "the",
        "city",
        "council",
        "approved",
        "a",
        "long-term",
        "plan",
    ]
    assert content_tokens("The city council approved a plan.", language="en") == [
        "the",
        "city",
        "council",
        "approved",
        "a",
        "plan",
    ]


def test_chinese_tokenization_uses_segmenter(monkeypatch) -> None:
    class FakeSegmenter:
        def cut(self, text: str) -> list[str]:
            return ["我", "喜欢", text[-2:]]

    monkeypatch.setattr(tokenizers, "_CHINESE_SEGMENTER", FakeSegmenter())
    assert is_chinese_language("zh-CN")
    assert tokenize("我喜欢中文", language="zh_CN") == ["我", "喜欢", "中文"]
