"""Scheduling-aware scoring utilities."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from moku_core.indexing.types import WeightedQueryTerm

URGENCY_DECAY = 0.22


@dataclass(frozen=True)
class ScheduleItem:
    word: str
    days_until_due: int
    interval_days: int


@dataclass(frozen=True)
class SchedulingScore:
    scheduling_score: float
    known_words: tuple[str, ...]
    due_words: tuple[str, ...]
    early_words: tuple[str, ...]
    requested_new_words: tuple[str, ...]
    unrequested_new_words: tuple[str, ...]


def due_query_terms(
    schedule: Sequence[ScheduleItem],
    requested_new_words: Iterable[str] = (),
    horizon_days: int = 14,
    urgency_decay: float = URGENCY_DECAY,
) -> list[WeightedQueryTerm]:
    query_terms = []
    included_words = set()
    for item in schedule:
        if item.days_until_due > horizon_days:
            continue
        scoring_days = max(item.days_until_due, 0)
        query_terms.append(
            WeightedQueryTerm(
                word=item.word,
                days_until_due=scoring_days,
                weight=math.exp(-urgency_decay * scoring_days),
            )
        )
        included_words.add(item.word)

    for word in requested_new_words:
        if word and word not in included_words:
            query_terms.append(WeightedQueryTerm(word=word, days_until_due=0, weight=1.0))
            included_words.add(word)

    return query_terms


def scheduling_word_penalty(
    word: str,
    schedule_by_word: Mapping[str, ScheduleItem],
    requested_new_words: set[str] | None = None,
) -> float:
    requested_new_words = requested_new_words or set()
    if word in schedule_by_word:
        item = schedule_by_word[word]
        days_until_due = max(int(item.days_until_due), 0)
        interval_days = max(int(item.interval_days), 1)
        return min(days_until_due / interval_days, 1.0)
    if word in requested_new_words:
        return 0.0
    return 1.0


def scheduling_score(
    content_tokens: Sequence[str],
    schedule: Sequence[ScheduleItem],
    requested_new_words: Iterable[str] = (),
) -> SchedulingScore:
    requested_new_word_set = set(requested_new_words)
    schedule_by_word = {item.word: item for item in schedule}
    words = sorted(set(content_tokens))

    if not words:
        return SchedulingScore(
            scheduling_score=1.0,
            known_words=(),
            due_words=(),
            early_words=(),
            requested_new_words=(),
            unrequested_new_words=(),
        )

    penalties = []
    known_words = []
    due_words = []
    early_words = []
    requested_hits = []
    unknown_words = []

    for word in words:
        penalty = scheduling_word_penalty(word, schedule_by_word, requested_new_word_set)
        penalties.append(penalty)
        if word in schedule_by_word:
            known_words.append(word)
            if schedule_by_word[word].days_until_due <= 0:
                due_words.append(word)
            else:
                early_words.append(word)
        elif word in requested_new_word_set:
            requested_hits.append(word)
        else:
            unknown_words.append(word)

    return SchedulingScore(
        scheduling_score=sum(penalties) / len(penalties),
        known_words=tuple(known_words),
        due_words=tuple(due_words),
        early_words=tuple(early_words),
        requested_new_words=tuple(requested_hits),
        unrequested_new_words=tuple(unknown_words),
    )
