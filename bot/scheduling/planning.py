from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.mappers import schedule_of
from bot.db.models import PENDING_STATES, OccurrenceRow, ReminderRow, ReminderState
from bot.domain.occurrences import OccurrenceKind
from bot.domain.reminders import Schedule, ScheduleKind
from bot.scheduling.recurrence import next_fire_after, to_utc


def first_fire(schedule: Schedule, tz: ZoneInfo, now: datetime) -> datetime | None:
    if schedule.kind is ScheduleKind.RRULE:
        return next_fire_after(schedule, tz, now - timedelta(microseconds=1))
    return to_utc(schedule.start, tz)


def new_main_occurrence(reminder: ReminderRow, fire_at: datetime) -> OccurrenceRow:
    return OccurrenceRow(
        reminder_id=reminder.id,
        user_id=reminder.user_id,
        kind=OccurrenceKind.MAIN,
        planned_at=fire_at,
        fire_at=fire_at,
    )


async def next_pending_fire(session: AsyncSession, reminder_id: str) -> datetime | None:
    return await session.scalar(
        select(func.min(OccurrenceRow.fire_at)).where(
            OccurrenceRow.reminder_id == reminder_id,
            OccurrenceRow.kind == OccurrenceKind.MAIN,
            OccurrenceRow.state.in_(PENDING_STATES),
        )
    )


async def advance_series(
    session: AsyncSession,
    reminder: ReminderRow,
    tz: ZoneInfo,
    resolved_planned_at: datetime,
    now: datetime,
) -> datetime | None:
    pending = await next_pending_fire(session, reminder.id)
    if pending is not None:
        return pending

    schedule = schedule_of(reminder)
    fire: datetime | None = None
    if schedule.kind is ScheduleKind.RRULE:
        fire = next_fire_after(schedule, tz, max(resolved_planned_at, now))
    elif schedule.kind is ScheduleKind.AFTER_COMPLETION and schedule.interval_after_done:
        fire = now + schedule.interval_after_done

    if fire is None:
        reminder.state = ReminderState.COMPLETED
        return None
    session.add(new_main_occurrence(reminder, fire))
    return fire
