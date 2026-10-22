from collections.abc import Sequence
from datetime import datetime, timedelta

from bot.domain.parsing import Alternative, ParseResult, ParseStatus
from bot.domain.reminders import DayPeriodDefaults, Nagging, Priority, ReminderDraft, Schedule
from bot.nlu.facts import (
    SCHEDULE_FACT_TYPES,
    Fact,
    NaggingFact,
    PreOffsetFact,
    PriorityFact,
    TagFact,
)
from bot.nlu.grammar import extract_facts
from bot.nlu.normalize import tokenize
from bot.nlu.schedule import resolve_schedule, to_timedelta
from bot.nlu.text import compose_text, consumed_pieces
from bot.nlu.tokens import Token, TokenKind
from bot.nlu.vocabulary import ANNIVERSARY_MARKERS

MAX_INPUT_LENGTH = 500
DEFAULT_NAGGING = Nagging(interval=timedelta(minutes=10), max_repeats=6)


def parse_reminder(text: str, now: datetime, day_periods: DayPeriodDefaults) -> ParseResult:
    if not text.strip() or len(text) > MAX_INPUT_LENGTH:
        return ParseResult(ParseStatus.NOT_UNDERSTOOD)
    tokenized = tokenize(text)
    extraction = extract_facts(tokenized.tokens)
    reminder_text = compose_text(
        tokenized.pieces, consumed_pieces(tokenized.tokens, extraction.consumed)
    )
    if not reminder_text:
        return ParseResult(ParseStatus.NOT_UNDERSTOOD)
    if not any(isinstance(fact, SCHEDULE_FACT_TYPES) for fact in extraction.facts):
        return ParseResult(ParseStatus.NEEDS_TIME, text=reminder_text)
    resolution = resolve_schedule(
        extraction.facts,
        now,
        day_periods,
        yearly_hint=mentions_anniversary(tokenized.tokens),
    )
    if resolution is None:
        return ParseResult(ParseStatus.NOT_UNDERSTOOD, text=reminder_text)
    build_draft = DraftBuilder(reminder_text, extraction.facts)
    return ParseResult(
        ParseStatus.OK,
        text=reminder_text,
        draft=build_draft(resolution.schedule),
        alternatives=tuple(
            Alternative(reading.label, build_draft(reading.schedule))
            for reading in resolution.alternatives
        ),
    )


class DraftBuilder:
    def __init__(self, text: str, facts: Sequence[Fact]) -> None:
        self.text = text
        self.tags = tuple(dict.fromkeys(fact.name for fact in facts if isinstance(fact, TagFact)))
        self.priority = max(
            (fact.priority for fact in facts if isinstance(fact, PriorityFact)),
            default=Priority.NORMAL,
        )
        offsets = {to_timedelta(fact.duration) for fact in facts if isinstance(fact, PreOffsetFact)}
        self.pre_offsets = tuple(sorted(offsets, reverse=True))
        self.nagging = (
            DEFAULT_NAGGING if any(isinstance(fact, NaggingFact) for fact in facts) else None
        )

    def __call__(self, schedule: Schedule) -> ReminderDraft:
        return ReminderDraft(
            text=self.text,
            schedule=schedule,
            tags=self.tags,
            priority=self.priority,
            pre_offsets=self.pre_offsets,
            nagging=self.nagging,
        )


def mentions_anniversary(tokens: Sequence[Token]) -> bool:
    return any(
        token.kind is TokenKind.WORD and token.text in ANNIVERSARY_MARKERS for token in tokens
    )
