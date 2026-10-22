from datetime import time
from typing import Any

from bot.db.models import ReminderRow, UserRow
from bot.domain.reminders import DayPeriodDefaults, Priority, Schedule, UserProfile

DAY_PERIOD_FIELDS = ("morning", "afternoon", "evening", "night", "date_only")


def schedule_of(reminder: ReminderRow) -> Schedule:
    return Schedule(
        kind=reminder.kind,
        start=reminder.dtstart_local,
        rrule=reminder.rrule,
        interval_after_done=reminder.interval_after_done,
    )


def apply_schedule(reminder: ReminderRow, schedule: Schedule) -> None:
    reminder.kind = schedule.kind
    reminder.dtstart_local = schedule.start
    reminder.rrule = schedule.rrule
    reminder.interval_after_done = schedule.interval_after_done


def priority_of(reminder: ReminderRow) -> Priority:
    return Priority(reminder.priority)


def profile_of(user: UserRow) -> UserProfile:
    return UserProfile(
        user_id=user.id,
        timezone=user.timezone,
        timezone_confirmed=user.timezone_confirmed,
        day_periods=day_periods_of(user.settings),
    )


def day_periods_of(settings: dict[str, Any]) -> DayPeriodDefaults:
    stored = settings.get("day_periods", {})
    overrides = {
        name: time.fromisoformat(stored[name]) for name in DAY_PERIOD_FIELDS if name in stored
    }
    return DayPeriodDefaults(**overrides)
