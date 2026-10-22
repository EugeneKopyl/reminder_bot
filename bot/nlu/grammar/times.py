from bot.nlu.facts import ClockFact, Fact, HourWindowFact, PeriodFact
from bot.nlu.grammar.common import take_time_point
from bot.nlu.grammar.cursor import Cursor
from bot.nlu.vocabulary import PERIOD_PHRASES, PERIOD_WORDS

CLOCK_PREPOSITIONS = frozenset({"в", "во", "к", "ко", "на", "около", "до"})


def match_clock(cursor: Cursor) -> list[Fact] | None:
    has_preposition = cursor.take_word(CLOCK_PREPOSITIONS) is not None
    first = take_time_point(cursor, bare_allowed=has_preposition)
    if first is None:
        return None
    clocks: list[Fact] = [first]
    while True:
        saved = cursor.position
        if not cursor.take_separator():
            break
        cursor.take_word(CLOCK_PREPOSITIONS)
        following = take_time_point(cursor, bare_allowed=True)
        if following is None:
            cursor.position = saved
            break
        clocks.append(following)
    return clocks


def match_hour_window(cursor: Cursor) -> list[Fact] | None:
    if cursor.take_word({"с", "со"}) is None:
        return None
    start = take_time_point(cursor, bare_allowed=True)
    if start is None or cursor.take_word({"до", "по"}) is None:
        return None
    end = take_time_point(cursor, bare_allowed=True)
    if end is None:
        return None
    return [HourWindowFact(start, align_window_end(start, end))]


def match_period(cursor: Cursor) -> list[Fact] | None:
    if cursor.word(1) == "рождения":
        return None
    period = cursor.take_lookup(PERIOD_WORDS)
    if period is None:
        first, second = cursor.word(), cursor.word(1)
        if first is None or second is None:
            return None
        period = PERIOD_PHRASES.get((first, second))
        if period is None:
            return None
        cursor.position += 2
    return [PeriodFact(period)]


def align_window_end(start: ClockFact, end: ClockFact) -> ClockFact:
    if end.ambiguous and (end.hour, end.minute) <= (start.hour, start.minute):
        return ClockFact(end.hour + 12, end.minute)
    return end
