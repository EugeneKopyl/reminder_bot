from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from bot.domain.reminders import DayPeriodDefaults, ReminderDraft


class ParseStatus(StrEnum):
    OK = "ok"
    NEEDS_TIME = "needs_time"
    NOT_UNDERSTOOD = "not_understood"


@dataclass(frozen=True, slots=True)
class Alternative:
    label: str
    draft: ReminderDraft


@dataclass(frozen=True, slots=True)
class ParseResult:
    status: ParseStatus
    text: str = ""
    draft: ReminderDraft | None = None
    alternatives: tuple[Alternative, ...] = ()


class ReminderParser(Protocol):
    def __call__(self, text: str, now: datetime, day_periods: DayPeriodDefaults) -> ParseResult:
        """`now` is timezone-aware in the user's timezone."""
        ...
