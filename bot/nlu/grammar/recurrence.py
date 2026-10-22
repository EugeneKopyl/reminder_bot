from bot.nlu.facts import (
    AfterCompletionFact,
    CountFact,
    Duration,
    Fact,
    FrequencyFact,
    MonthDaySetFact,
    PeriodFact,
    ShiftFact,
    Unit,
    WeekdaySetFact,
)
from bot.nlu.grammar.common import take_completion_reference, take_durations, take_weekday_list
from bot.nlu.grammar.cursor import Cursor
from bot.nlu.vocabulary import (
    ADVERB_FREQUENCIES,
    EVERY_WORDS,
    LAST_WORDS,
    MONTH_DAY_WORDS,
    PLURAL_PERIODS,
    RECURRING_PERIODS,
    UNITS,
    WEEKDAYS_ACCUSATIVE,
    WEEKDAYS_PLURAL_DATIVE,
    WEEKEND,
    WORKDAYS,
)

WORKDAY_GROUP_DATIVE = (("будням",), ("рабочим", "дням"), ("будним", "дням"))
WEEKEND_GROUP_DATIVE = (("выходным", "дням"), ("выходным",))
WORKDAY_GROUP_ACCUSATIVE = (("будни",), ("будние", "дни"), ("рабочие", "дни"))
EVERY_WORKDAY = (("будний", "день"), ("рабочий", "день"))


def match_shift(cursor: Cursor) -> list[Fact] | None:
    if cursor.take_word({"через"}) is None:
        return None
    durations = take_durations(cursor)
    if not durations:
        return None
    if take_completion_reference(cursor):
        return [AfterCompletionFact(durations)]
    return [ShiftFact(durations)]


def match_frequency(cursor: Cursor) -> list[Fact] | None:
    facts = take_frequency(cursor)
    if facts is None:
        return None
    frequency = facts[0]
    if isinstance(frequency, FrequencyFact) and take_completion_reference(cursor):
        duration = Duration(frequency.interval, frequency.unit)
        return [AfterCompletionFact((duration,)), *facts[1:]]
    return facts


def take_frequency(cursor: Cursor) -> list[Fact] | None:
    if (unit := cursor.take_lookup(ADVERB_FREQUENCIES)) is not None:
        return [FrequencyFact(unit)]
    if cursor.take_word({"по"}):
        period = cursor.take_lookup(PLURAL_PERIODS)
        return [FrequencyFact(Unit.DAY), PeriodFact(period)] if period is not None else None
    if cursor.take_words("раз", "в"):
        return take_interval_and_unit(cursor)
    if cursor.take_word(EVERY_WORDS) is None:
        return None
    if (period := cursor.take_lookup(RECURRING_PERIODS)) is not None:
        return [FrequencyFact(Unit.DAY), PeriodFact(period)]
    return take_interval_and_unit(cursor)


def take_interval_and_unit(cursor: Cursor) -> list[Fact] | None:
    interval = cursor.take_number(1, 999)
    unit = cursor.take_lookup(UNITS)
    if unit is None:
        return None
    return [FrequencyFact(unit, interval.value if interval is not None else 1)]


def match_weekday_set(cursor: Cursor) -> list[Fact] | None:
    if cursor.take_word({"по"}):
        return take_dative_weekdays(cursor)
    if cursor.take_word({"в", "во"}):
        return take_monthly_weekdays(cursor)
    if cursor.take_word(EVERY_WORDS):
        return take_every_weekdays(cursor)
    return None


def take_dative_weekdays(cursor: Cursor) -> list[Fact] | None:
    weekdays = take_weekday_list(cursor, WEEKDAYS_PLURAL_DATIVE, frozenset({"по"}))
    if weekdays:
        return [WeekdaySetFact(tuple(weekdays))]
    if any(cursor.take_words(*phrase) for phrase in WORKDAY_GROUP_DATIVE):
        return [WeekdaySetFact(WORKDAYS)]
    if any(cursor.take_words(*phrase) for phrase in WEEKEND_GROUP_DATIVE):
        return [WeekdaySetFact(WEEKEND)]
    return None


def take_monthly_weekdays(cursor: Cursor) -> list[Fact] | None:
    if any(cursor.take_words(*phrase) for phrase in WORKDAY_GROUP_ACCUSATIVE):
        return [WeekdaySetFact(WORKDAYS)]
    ordinal = take_weekday_ordinal(cursor)
    if ordinal is None:
        return None
    weekdays = take_weekday_list(cursor, WEEKDAYS_ACCUSATIVE)
    if not weekdays or not cursor.take_word({"месяца"}):
        return None
    return [WeekdaySetFact(tuple(weekdays), ordinal)]


def take_every_weekdays(cursor: Cursor) -> list[Fact] | None:
    if any(cursor.take_words(*phrase) for phrase in EVERY_WORKDAY):
        return [WeekdaySetFact(WORKDAYS)]
    if cursor.take_word({"выходные"}):
        return [WeekdaySetFact(WEEKEND)]
    ordinal = take_weekday_ordinal(cursor)
    weekdays = take_weekday_list(cursor, WEEKDAYS_ACCUSATIVE)
    if not weekdays:
        return None
    cursor.take_word({"месяца"})
    return [WeekdaySetFact(tuple(weekdays), ordinal)]


def take_weekday_ordinal(cursor: Cursor) -> int | None:
    if cursor.take_word(LAST_WORDS):
        return -1
    token = cursor.take_number(1, 5, ordinal=True)
    return token.value if token is not None else None


def match_month_day_set(cursor: Cursor) -> list[Fact] | None:
    if cursor.take_word(EVERY_WORDS):
        if cursor.take_word(LAST_WORDS):
            if cursor.take_word({"день", *MONTH_DAY_WORDS}) is None:
                return None
            cursor.take_word({"месяца"})
            return [MonthDaySetFact((-1,)), FrequencyFact(Unit.MONTH)]
        token = cursor.take_number(1, 31)
        if token is None:
            return None
        if cursor.take_word(MONTH_DAY_WORDS) is None and not token.ordinal:
            return None
        if not cursor.take_words("каждого", "месяца"):
            cursor.take_word({"месяца"})
        return [MonthDaySetFact((token.value,))]
    cursor.take_word({"в"})
    if cursor.take_word(LAST_WORDS) is None:
        return None
    unit_word = cursor.take_word({"день", *MONTH_DAY_WORDS})
    has_month = cursor.take_word({"месяца"}) is not None
    if unit_word is None or (unit_word == "день" and not has_month):
        return None
    return [MonthDaySetFact((-1,)), FrequencyFact(Unit.MONTH)]


def match_count(cursor: Cursor) -> list[Fact] | None:
    qualified = cursor.take_word({"всего", "только"}) is not None
    token = cursor.take_number(1, 999, ordinal=False)
    if token is None or cursor.take_word({"раз", "раза"}) is None:
        return None
    in_a_row = cursor.take_word({"подряд"}) is not None
    if qualified or in_a_row or cursor.follows_match:
        return [CountFact(token.value)]
    return None
