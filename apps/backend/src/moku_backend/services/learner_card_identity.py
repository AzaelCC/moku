"""Shared learner note/card identity helpers."""

from __future__ import annotations

import re

CARD_WORD_MAX_LENGTH = 255
CARD_TYPE_MAX_LENGTH = 120

CARD_TYPE_SEPARATOR_RE = re.compile(r"[\s/\\]+")
CARD_TYPE_INVALID_RE = re.compile(r"[^a-z0-9:_-]+")


def normalize_word(value: str) -> str:
    word = value.strip().casefold()
    if not word:
        raise ValueError("Learner card word must not be empty.")
    if len(word) > CARD_WORD_MAX_LENGTH:
        raise ValueError(f"Learner card word must be {CARD_WORD_MAX_LENGTH} characters or fewer.")
    return word


def normalize_card_type(value: str) -> str:
    card_type = value.strip().casefold()
    card_type = CARD_TYPE_SEPARATOR_RE.sub("_", card_type)
    card_type = CARD_TYPE_INVALID_RE.sub("_", card_type)
    card_type = re.sub(r"_+", "_", card_type).strip("_")
    if not card_type:
        raise ValueError("Learner card type must not be empty.")
    if len(card_type) > CARD_TYPE_MAX_LENGTH:
        raise ValueError(
            f"Learner card type must be {CARD_TYPE_MAX_LENGTH} characters or fewer."
        )
    return card_type


def manual_note_key(word: str) -> str:
    return f"manual:{word}"


def anki_note_key(note_id: int) -> str:
    return f"anki:{note_id}"


def anki_card_type(
    *,
    template_name: str | None,
    ord_value: int | None,
    card_id: int,
) -> str:
    if template_name:
        return normalize_card_type(template_name)
    if ord_value is not None:
        return normalize_card_type(f"anki:{ord_value}")
    return normalize_card_type(f"anki_card:{card_id}")
