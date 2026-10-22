from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import IntEnum, StrEnum


class ScheduleKind(StrEnum):
    ONCE = "once"
    RRULE = "rrule"
    AFTER_COMPLETION = "after_completion"


class Priority(IntEnum):
    NORMAL = 0
    IMPORTANT = 1
    CRITICAL = 2


@dataclass(frozen=True, slots=True)
class Schedule:
    """`start` is a naive wall-clock datetime in the owner's timezone.

    `rrule` holds RFC 5545 rule parts without DTSTART, e.g. "FREQ=DAILY;BYHOUR=8,20;BYMINUTE=0".
    """

    kind: ScheduleKind
    start: datetime
    rrule: str | None = None
    interval_after_done: timedelta | None = None


@dataclass(frozen=True, slots=True)
class Nagging:
    interval: timedelta
    max_repeats: int


@dataclass(frozen=True, slots=True)
class ReminderDraft:
    text: str
    schedule: Schedule
    tags: tuple[str, ...] = ()
    priority: Priority = Priority.NORMAL
    pre_offsets: tuple[timedelta, ...] = ()
    nagging: Nagging | None = None


@dataclass(frozen=True, slots=True)
class DayPeriodDefaults:
    morning: time = time(9)
    afternoon: time = time(13)
    evening: time = time(19)
    night: time = time(22)
    date_only: time = time(9)
