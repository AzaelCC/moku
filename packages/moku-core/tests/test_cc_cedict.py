from __future__ import annotations

import pytest
from moku_core.dictionary import (
    CcCedictParseError,
    parse_cc_cedict_line,
    parse_cc_cedict_lines,
)


def test_parse_cc_cedict_line_skips_comments_and_blank_lines() -> None:
    assert parse_cc_cedict_line("# comment") is None
    assert parse_cc_cedict_line("   ") is None


def test_parse_cc_cedict_v1_entry_preserves_spaced_pinyin() -> None:
    entry = parse_cc_cedict_line(
        "\u5b78\u7fd2 \u5b66\u4e60 [xue2 xi2] /to learn/to study/",
        line_number=12,
    )

    assert entry is not None
    assert entry.traditional == "\u5b78\u7fd2"
    assert entry.simplified == "\u5b66\u4e60"
    assert entry.pinyin == "xue2 xi2"
    assert entry.pinyin_format == "v1"
    assert entry.senses == (("to learn",), ("to study",))
    assert entry.line_number == 12


def test_parse_cc_cedict_v2_entry_splits_senses_and_glosses() -> None:
    entry = parse_cc_cedict_line(
        "\u7b97 \u7b97 [[suan4]] "
        "/to calculate; to figure out/to include; to count in/"
    )

    assert entry is not None
    assert entry.pinyin == "suan4"
    assert entry.pinyin_format == "v2"
    assert entry.senses == (
        ("to calculate", "to figure out"),
        ("to include", "to count in"),
    )


def test_parse_cc_cedict_lines_tracks_source_line_numbers() -> None:
    entries = list(
        parse_cc_cedict_lines(
            [
                "# header\n",
                "\u738b \u738b [[Wang2]] /surname Wang/\n",
                "\u738b \u738b [[wang2]] /king/\n",
            ]
        )
    )

    assert [entry.pinyin for entry in entries] == ["Wang2", "wang2"]
    assert [entry.line_number for entry in entries] == [2, 3]


def test_parse_cc_cedict_rejects_malformed_lines() -> None:
    with pytest.raises(CcCedictParseError, match="line 4"):
        parse_cc_cedict_line("not a cedict row", line_number=4)


def test_parse_cc_cedict_rejects_empty_definitions() -> None:
    with pytest.raises(CcCedictParseError, match="Empty"):
        parse_cc_cedict_line("\u5b78 \u5b66 [[xue2]] //")
