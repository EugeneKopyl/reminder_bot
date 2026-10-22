from bot.nlu.facts import (
    DateFact,
    DayOffsetFact,
    Fact,
    MonthDayFact,
    PeriodEndFact,
    StartFact,
    Unit,
    UntilFact,
    WeekdayFact,
)
from bot.nlu.grammar.common import take_calendar_date, take_weekday_list
from bot.nlu.grammar.cursor import Cursor
from bot.nlu.vocabulary import (
    DAY_OFFSETS,
    DAY_OFFSETS_GENITIVE,
    MONTH_DAY_WORDS,
    MONTHS,
    WEEKDAY_QUALIFIERS,
    WEEKDAYS_ACCUSATIVE,
    WEEKDAYS_GENITIVE,
    WEEKEND,
)

DATE_PREPOSITIONS = frozenset({"в", "во", "на", "к", "ко"})
PERIOD_END_UNITS = {"недели": Unit.WEEK, "месяца": Unit.MONTH, "года": Unit.YEAR}


def match_until(cursor: Cursor) -> list[Fact] | None:
    if cursor.take_word({"до", "по"}) is None:
        return None
    target = take_bound_target(cursor)
    return [UntilFact(target)] if target is not None else None


def match_start(cursor: Cursor) -> list[Fact] | None:
    explicit = cursor.take_word({"начиная"}) is not None
    if cursor.take_word({"с", "со"}) is None and not explicit:
        return None
    target = take_start_target(cursor)
    return [StartFact(target)] if target is not None else None


def match_calendar_date(cursor: Cursor) -> list[Fact] | None:
    cursor.take_word(DATE_PREPOSITIONS)
    date = take_calendar_date(cursor)
    return [date] if date is not None else None


def match_month_day(cursor: Cursor) -> list[Fact] | None:
    cursor.take_word(DATE_PREPOSITIONS)
    token = cursor.take_number(1, 31)
    if token is None:
        return None
    if cursor.take_word(MONTH_DAY_WORDS) or (token.ordinal and not token.spoken):
        return [MonthDayFact(token.value)]
    return None


def match_day_offset(cursor: Cursor) -> list[Fact] | None:
    cursor.take_word(DATE_PREPOSITIONS)
    days = cursor.take_lookup(DAY_OFFSETS)
    return [DayOffsetFact(days)] if days is not None else None


def match_weekday(cursor: Cursor) -> list[Fact] | None:
    has_preposition = cursor.take_word(DATE_PREPOSITIONS) is not None
    next_week = cursor.take_lookup(WEEKDAY_QUALIFIERS)
    if not has_preposition and next_week is None:
        return None
    if next_week and cursor.take_word({"неделе"}):
        return [WeekdayFact(0, next_week=True)]
    if cursor.take_word({"выходные", "выходных"}):
        return [WeekdayFact(WEEKEND[0], next_week=bool(next_week))]
    weekdays = take_weekday_list(cursor, WEEKDAYS_ACCUSATIVE, DATE_PREPOSITIONS)
    return [WeekdayFact(weekday, next_week=bool(next_week)) for weekday in weekdays] or None


def take_bound_target(cursor: Cursor) -> DateFact | None:
    if cursor.take_word({"конца"}):
        unit = cursor.take_lookup(PERIOD_END_UNITS)
        if unit is not None:
            return PeriodEndFact(unit)
        month = cursor.take_lookup(MONTHS)
        return PeriodEndFact(Unit.MONTH, month) if month is not None else None
    if (date := take_calendar_date(cursor)) is not None:
        return date
    if (weekday := cursor.take_lookup(WEEKDAYS_GENITIVE)) is not None:
        return WeekdayFact(weekday)
    if (days := cursor.take_lookup(DAY_OFFSETS)) is not None:
        return DayOffsetFact(days)
    return None


def take_start_target(cursor: Cursor) -> DateFact | None:
    if (date := take_calendar_date(cursor)) is not None:
        return date
    if (weekday := cursor.take_lookup(WEEKDAYS_GENITIVE)) is not None:
        return WeekdayFact(weekday)
    if (days := cursor.take_lookup(DAY_OFFSETS)) is not None:
        return DayOffsetFact(days)
    if (days := cursor.take_lookup(DAY_OFFSETS_GENITIVE)) is not None:
        cursor.take_word({"дня"})
        return DayOffsetFact(days)
    if cursor.take_words("следующей", "недели"):
        return WeekdayFact(0, next_week=True)
    if cursor.take_words("следующего", "месяца"):
        return MonthDayFact(1)
    token = cursor.take_number(1, 31)
    if token is not None and cursor.take_word(MONTH_DAY_WORDS):
        return MonthDayFact(token.value)
    return None
