from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from bot.domain.reminders import Priority, Schedule


class OccurrenceKind(StrEnum):
    MAIN = "main"
    PRE = "pre"
    NAG = "nag"


@dataclass(frozen=True, slots=True)
class Done:
    pass


@dataclass(frozen=True, slots=True)
class SnoozeFor:
    delta: timedelta


@dataclass(frozen=True, slots=True)
class SnoozeUntil:
    local_time: datetime


@dataclass(frozen=True, slots=True)
class Skip:
    pass


@dataclass(frozen=True, slots=True)
class StopSeries:
    pass


OccurrenceAction = Done | SnoozeFor | SnoozeUntil | Skip | StopSeries


@dataclass(frozen=True, slots=True)
class ActionOutcome:
    applied: bool
    next_fire_at: datetime | None = None
    series_finished: bool = False


@dataclass(frozen=True, slots=True)
class Notification:
    occurrence_id: int
    reminder_id: str
    user_id: int
    kind: OccurrenceKind
    card_message_id: int | None
    schedule: Schedule
    priority: Priority
    planned_at: datetime
    overdue_by: timedelta


@dataclass(frozen=True, slots=True)
class PlannedFire:
    reminder_id: str
    at: datetime
    schedule: Schedule
    priority: Priority
    card_message_id: int | None


@dataclass(frozen=True, slots=True)
class ReminderSummary:
    reminder_id: str
    schedule: Schedule
    priority: Priority
    next_fire_at: datetime | None
    card_message_id: int | None
