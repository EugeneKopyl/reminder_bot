from collections.abc import Callable, Sequence
from dataclasses import dataclass

from bot.nlu.facts import Fact
from bot.nlu.grammar.cursor import SEPARATORS, Cursor
from bot.nlu.grammar.dates import (
    match_calendar_date,
    match_day_offset,
    match_month_day,
    match_start,
    match_until,
    match_weekday,
)
from bot.nlu.grammar.modifiers import (
    match_hashtag,
    match_nagging,
    match_pre_offset,
    match_priority,
    match_tag_word,
)
from bot.nlu.grammar.recurrence import (
    match_count,
    match_frequency,
    match_month_day_set,
    match_shift,
    match_weekday_set,
)
from bot.nlu.grammar.times import match_clock, match_hour_window, match_period
from bot.nlu.tokens import Token

Matcher = Callable[[Cursor], list[Fact] | None]

MATCHERS: tuple[Matcher, ...] = (
    match_hashtag,
    match_tag_word,
    match_priority,
    match_nagging,
    match_pre_offset,
    match_shift,
    match_frequency,
    match_weekday_set,
    match_month_day_set,
    match_hour_window,
    match_until,
    match_start,
    match_count,
    match_calendar_date,
    match_month_day,
    match_day_offset,
    match_weekday,
    match_clock,
    match_period,
)


@dataclass(frozen=True, slots=True)
class Extraction:
    facts: tuple[Fact, ...]
    consumed: tuple[bool, ...]


def extract_facts(tokens: Sequence[Token]) -> Extraction:
    facts: list[Fact] = []
    consumed = [False] * len(tokens)
    position = 0
    while position < len(tokens):
        follows_match = position > 0 and consumed[position - 1]
        match = first_match(tokens, position, follows_match=follows_match)
        if match is None:
            position += 1
            continue
        end, matched_facts = match
        facts.extend(matched_facts)
        consumed[position:end] = [True] * (end - position)
        position = end
    absorb_separators(tokens, consumed)
    return Extraction(tuple(facts), tuple(consumed))


def first_match(
    tokens: Sequence[Token], position: int, *, follows_match: bool
) -> tuple[int, list[Fact]] | None:
    for matcher in MATCHERS:
        cursor = Cursor(tokens, position, follows_match=follows_match)
        facts = matcher(cursor)
        if facts and cursor.position > position:
            return cursor.position, facts
    return None


def absorb_separators(tokens: Sequence[Token], consumed: list[bool]) -> None:
    for index in range(1, len(tokens) - 1):
        if tokens[index].text in SEPARATORS and consumed[index - 1] and consumed[index + 1]:
            consumed[index] = True
