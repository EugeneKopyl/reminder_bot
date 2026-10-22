from dataclasses import dataclass
from enum import StrEnum

from bot.domain.reminders import Priority


class Unit(StrEnum):
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"

    @property
    def is_sub_daily(self) -> bool:
        return self in (Unit.MINUTE, Unit.HOUR)


class DayPeriod(StrEnum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    NIGHT = "night"


@dataclass(frozen=True, slots=True)
class Duration:
    amount: int
    unit: Unit


@dataclass(frozen=True, slots=True)
class ClockFact:
    hour: int
    minute: int
    ambiguous: bool = False

    def in_period(self, period: DayPeriod) -> "ClockFact":
        return ClockFact(hour_in_period(self.hour, period), self.minute)


def hour_in_period(hour: int, period: DayPeriod) -> int:
    if hour > 12:
        return hour
    if period is DayPeriod.MORNING:
        return 0 if hour == 12 else hour
    if period is DayPeriod.AFTERNOON:
        return hour + 12 if 1 <= hour <= 6 else hour
    if period is DayPeriod.EVENING:
        return hour + 12 if 1 <= hour <= 11 else hour
    if hour == 12:
        return 0
    return hour + 12 if 9 <= hour <= 11 else hour


@dataclass(frozen=True, slots=True)
class PeriodFact:
    period: DayPeriod


@dataclass(frozen=True, slots=True)
class DayOffsetFact:
    days: int


@dataclass(frozen=True, slots=True)
class CalendarDateFact:
    day: int
    month: int
    year: int | None = None


@dataclass(frozen=True, slots=True)
class MonthDayFact:
    day: int


@dataclass(frozen=True, slots=True)
class WeekdayFact:
    weekday: int
    next_week: bool = False


@dataclass(frozen=True, slots=True)
class PeriodEndFact:
    unit: Unit
    month: int | None = None


DateFact = CalendarDateFact | DayOffsetFact | MonthDayFact | WeekdayFact | PeriodEndFact


@dataclass(frozen=True, slots=True)
class ShiftFact:
    durations: tuple[Duration, ...]


@dataclass(frozen=True, slots=True)
class AfterCompletionFact:
    durations: tuple[Duration, ...]


@dataclass(frozen=True, slots=True)
class FrequencyFact:
    unit: Unit
    interval: int = 1


@dataclass(frozen=True, slots=True)
class WeekdaySetFact:
    weekdays: tuple[int, ...]
    ordinal: int | None = None


@dataclass(frozen=True, slots=True)
class MonthDaySetFact:
    days: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class HourWindowFact:
    start: ClockFact
    end: ClockFact


@dataclass(frozen=True, slots=True)
class UntilFact:
    target: DateFact


@dataclass(frozen=True, slots=True)
class StartFact:
    target: DateFact


@dataclass(frozen=True, slots=True)
class CountFact:
    count: int


@dataclass(frozen=True, slots=True)
class PreOffsetFact:
    duration: Duration


@dataclass(frozen=True, slots=True)
class PriorityFact:
    priority: Priority


@dataclass(frozen=True, slots=True)
class NaggingFact:
    pass


@dataclass(frozen=True, slots=True)
class TagFact:
    name: str


ScheduleFact = (
    ClockFact
    | PeriodFact
    | DayOffsetFact
    | CalendarDateFact
    | MonthDayFact
    | WeekdayFact
    | ShiftFact
    | AfterCompletionFact
    | FrequencyFact
    | WeekdaySetFact
    | MonthDaySetFact
    | HourWindowFact
    | UntilFact
    | StartFact
    | CountFact
)

Fact = ScheduleFact | PreOffsetFact | PriorityFact | NaggingFact | TagFact

SCHEDULE_FACT_TYPES: tuple[type, ...] = (
    ClockFact,
    PeriodFact,
    DayOffsetFact,
    CalendarDateFact,
    MonthDayFact,
    WeekdayFact,
    ShiftFact,
    AfterCompletionFact,
    FrequencyFact,
    WeekdaySetFact,
    MonthDaySetFact,
    HourWindowFact,
    UntilFact,
    StartFact,
)
