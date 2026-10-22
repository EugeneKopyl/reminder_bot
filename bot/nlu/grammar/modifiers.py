from bot.domain.reminders import Priority
from bot.nlu.facts import Fact, NaggingFact, PreOffsetFact, PriorityFact, TagFact
from bot.nlu.grammar.common import take_duration
from bot.nlu.grammar.cursor import Cursor
from bot.nlu.tokens import TokenKind
from bot.nlu.vocabulary import (
    DAY_OFFSETS,
    MONTHS,
    PRIORITY_INTENSIFIERS,
    PRIORITY_SYMBOLS,
    PRIORITY_WORDS,
    WEEKDAYS_GENITIVE,
)

TAG_WORDS = frozenset({"тег", "тегом", "метка", "меткой"})
CONFIRMATION_WORDS = frozenset({"подтверждения", "ответа", "отметки"})
DATE_WORDS = frozenset({*WEEKDAYS_GENITIVE, *MONTHS, *DAY_OFFSETS, "конца"})


def match_hashtag(cursor: Cursor) -> list[Fact] | None:
    token = cursor.take_kind(TokenKind.HASHTAG)
    return [TagFact(token.text)] if token is not None else None


def match_tag_word(cursor: Cursor) -> list[Fact] | None:
    cursor.take_word({"с"})
    if cursor.take_word(TAG_WORDS) is None:
        return None
    name = cursor.word()
    if name is None:
        return None
    cursor.advance()
    return [TagFact(name)]


def match_priority(cursor: Cursor) -> list[Fact] | None:
    if cursor.take_word(PRIORITY_INTENSIFIERS):
        return [PriorityFact(Priority.CRITICAL)] if cursor.take_word({"важно"}) else None
    priority = cursor.take_lookup(PRIORITY_WORDS) or cursor.take_symbol_lookup(PRIORITY_SYMBOLS)
    return [PriorityFact(priority)] if priority is not None else None


def match_nagging(cursor: Cursor) -> list[Fact] | None:
    if cursor.take_word({"настойчиво"}):
        return [NaggingFact()]
    if cursor.take_words("пока", "не"):
        if cursor.word() is None:
            return None
        cursor.advance()
        return [NaggingFact()]
    if cursor.take_word({"до"}) and cursor.take_word(CONFIRMATION_WORDS):
        return [NaggingFact()]
    return None


def match_pre_offset(cursor: Cursor) -> list[Fact] | None:
    facts: list[Fact] = []
    while True:
        saved = cursor.position
        if facts and not cursor.take_separator():
            break
        duration = take_duration(cursor) if cursor.take_word({"за"}) else None
        if duration is None:
            cursor.position = saved
            break
        facts.append(PreOffsetFact(duration))
    if facts:
        take_event_reference(cursor)
    return facts or None


def take_event_reference(cursor: Cursor) -> None:
    following = cursor.word(1)
    if cursor.word() != "до" or following is None or following in DATE_WORDS:
        return
    cursor.position += 2
