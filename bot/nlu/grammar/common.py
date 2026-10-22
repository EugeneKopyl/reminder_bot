import calendar
from collections.abc import Mapping

from bot.nlu.facts import CalendarDateFact, ClockFact, Duration
from bot.nlu.grammar.cursor import Cursor
from bot.nlu.tokens import TokenKind
from bot.nlu.vocabulary import (
    COMPLETION_REFERENCE_QUALIFIERS,
    EVERY_WORDS,
    HOUR_WORDS,
    MERIDIEMS,
    MINUTE_WORDS,
    MONTHS,
    NAMED_TIMES,
    NON_COMPLETION_REFERENCES,
    UNITS,
    YEAR_WORDS,
    can_follow_time,
)

LEAP_YEAR = 2028


def take_duration(cursor: Cursor) -> Duration | None:
    saved = cursor.position
    amount = cursor.take_number(1, 999, ordinal=False)
    unit = cursor.take_lookup(UNITS)
    if unit is None:
        cursor.position = saved
        return None
    return Duration(amount.value if amount is not None else 1, unit)


def take_durations(cursor: Cursor) -> tuple[Duration, ...]:
    durations: list[Duration] = []
    while (duration := take_duration(cursor)) is not None:
        durations.append(duration)
        saved = cursor.position
        if not cursor.take_word({"и"}):
            continue
        following = take_duration(cursor)
        if following is None:
            cursor.position = saved
            break
        durations.append(following)
    return tuple(durations)


def take_completion_reference(cursor: Cursor) -> bool:
    saved = cursor.position
    if cursor.take_word({"после", "от"}) is None:
        return False
    if not cursor.take_words("того", "как"):
        cursor.take_word(COMPLETION_REFERENCE_QUALIFIERS)
    reference = cursor.word()
    if reference is None or reference in NON_COMPLETION_REFERENCES:
        cursor.position = saved
        return False
    cursor.advance()
    return True


def take_calendar_date(cursor: Cursor) -> CalendarDateFact | None:
    saved = cursor.position
    token = cursor.peek()
    if token is not None and token.kind is TokenKind.DOTTED:
        cursor.advance()
        dotted = parse_dotted_date(token.text)
        if dotted is None:
            cursor.position = saved
        return dotted
    day = cursor.take_number(1, 31)
    month = cursor.take_lookup(MONTHS) if day is not None else None
    if day is None or month is None:
        cursor.position = saved
        return None
    year = take_year(cursor)
    if not is_valid_day(day.value, month, year):
        cursor.position = saved
        return None
    return CalendarDateFact(day.value, month, year)


def take_year(cursor: Cursor) -> int | None:
    token = cursor.take_number(2000, 2100, ordinal=False)
    if token is None:
        return None
    cursor.take_word(YEAR_WORDS)
    return token.value


def parse_dotted_date(text: str) -> CalendarDateFact | None:
    parts = [int(part) for part in text.split(".")]
    day, month = parts[0], parts[1]
    year = None
    if len(parts) == 3:
        year = parts[2] + 2000 if parts[2] < 100 else parts[2]
    if not 1 <= month <= 12 or not is_valid_day(day, month, year):
        return None
    return CalendarDateFact(day, month, year)


def is_valid_day(day: int, month: int, year: int | None) -> bool:
    return 1 <= day <= calendar.monthrange(year or LEAP_YEAR, month)[1]


def take_time_point(cursor: Cursor, *, bare_allowed: bool) -> ClockFact | None:
    token = cursor.peek()
    if token is None:
        return None
    clock: ClockFact | None = None
    if token.kind is TokenKind.CLOCK:
        cursor.advance()
        cursor.take_word(MINUTE_WORDS)
        clock = ClockFact(token.value, token.minute, token.has_ambiguous_hour)
    elif token.kind is TokenKind.DOTTED and bare_allowed:
        clock = parse_dotted_clock(token.text)
        if clock is not None:
            cursor.advance()
    elif token.kind is TokenKind.WORD and token.text in NAMED_TIMES and bare_allowed:
        cursor.advance()
        hour, minute = NAMED_TIMES[token.text]
        return ClockFact(hour, minute)
    elif token.kind is TokenKind.WORD and token.text == "час" and bare_allowed:
        cursor.advance()
        clock = ClockFact(1, 0, ambiguous=True)
    elif token.kind is TokenKind.NUMBER and not token.ordinal and token.value <= 24:
        if bare_allowed or cursor.word(1) in MERIDIEMS:
            clock = take_numeric_clock(cursor)
    if clock is None:
        return None
    period = cursor.take_lookup(MERIDIEMS)
    return clock.in_period(period) if period is not None else clock


def take_numeric_clock(cursor: Cursor) -> ClockFact | None:
    saved = cursor.position
    hour = cursor.advance().value % 24
    cursor.take_word(HOUR_WORDS)
    minute = 0
    after_hour = cursor.position
    minute_token = cursor.take_number(0, 59, ordinal=False)
    if minute_token is not None and cursor.take_word(MINUTE_WORDS):
        minute = minute_token.value
    else:
        cursor.position = after_hour
    follower = cursor.word()
    if follower is not None and follower not in MERIDIEMS and not can_follow_time(follower):
        cursor.position = saved
        return None
    return ClockFact(hour, minute, ambiguous=1 <= hour <= 11)


def parse_dotted_clock(text: str) -> ClockFact | None:
    parts = text.split(".")
    if len(parts) != 2 or len(parts[1]) != 2:
        return None
    hour, minute = int(parts[0]), int(parts[1])
    if hour > 23 or minute > 59:
        return None
    return ClockFact(hour, minute)


def take_weekday_list(
    cursor: Cursor, table: Mapping[str, int], prepositions: frozenset[str] = frozenset()
) -> list[int]:
    first = cursor.take_lookup(table)
    if first is None:
        return []
    weekdays = [first]
    while True:
        saved = cursor.position
        if not cursor.take_separator():
            break
        cursor.take_word(prepositions | EVERY_WORDS)
        weekday = cursor.take_lookup(table)
        if weekday is None:
            cursor.position = saved
            break
        if weekday not in weekdays:
            weekdays.append(weekday)
    return weekdays
