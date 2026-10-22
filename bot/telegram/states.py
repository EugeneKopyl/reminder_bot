from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from aiogram.fsm.state import State, StatesGroup

from bot.domain.reminders import Schedule, ScheduleKind


class PendingReminder(StatesGroup):
    waiting_time = State()


class EditReminder(StatesGroup):
    waiting_schedule = State()


class SnoozeOccurrence(StatesGroup):
    waiting_time = State()


class TimezoneInput(StatesGroup):
    waiting_name = State()


def dump_schedule(schedule: Schedule) -> dict[str, Any]:
    interval = schedule.interval_after_done
    return {
        "kind": schedule.kind.value,
        "start": schedule.start.isoformat(),
        "rrule": schedule.rrule,
        "interval_after_done": interval.total_seconds() if interval is not None else None,
    }


def load_schedule(data: Mapping[str, Any]) -> Schedule:
    interval = data.get("interval_after_done")
    return Schedule(
        kind=ScheduleKind(data["kind"]),
        start=datetime.fromisoformat(data["start"]),
        rrule=data.get("rrule"),
        interval_after_done=timedelta(seconds=interval) if interval is not None else None,
    )


ALTERNATIVES_KEY = "alternatives"
PENDING_TEXT_KEY = "pending_text"
PENDING_MESSAGE_KEY = "pending_message_id"
TARGET_REMINDER_KEY = "reminder_id"
TARGET_MESSAGE_KEY = "message_id"
TARGET_OCCURRENCE_KEY = "occurrence_id"
