from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from bot.db.engine import SessionFactory
from bot.db.models import OccurrenceState
from bot.domain.occurrences import Done, Skip, SnoozeFor, SnoozeUntil, StopSeries
from bot.domain.reminders import (
    DayPeriodDefaults,
    Nagging,
    Priority,
    ReminderDraft,
    Schedule,
    ScheduleKind,
)
from bot.services.reminders import SqlReminderService
from tests.reminders.conftest import (
    DEFAULT_TIMEZONE,
    OTHER_USER_ID,
    USER_ID,
    FakeClock,
    WakeCounter,
    occurrences_of,
    once_draft,
    pending_occurrence,
    rrule_draft,
)

MOSCOW = ZoneInfo("Europe/Moscow")


async def test_new_user_gets_default_profile(service: SqlReminderService) -> None:
    profile = await service.ensure_user(USER_ID)

    assert profile.timezone == DEFAULT_TIMEZONE
    assert not profile.timezone_confirmed
    assert profile.day_periods == DayPeriodDefaults()
    assert await service.ensure_user(USER_ID) == profile


async def test_set_timezone_confirms_and_shifts_floating_reminders(
    service: SqlReminderService, session_factory: SessionFactory
) -> None:
    reminder_id = await service.create_reminder(USER_ID, once_draft(datetime(2026, 10, 22, 18, 0)))

    profile = await service.set_timezone(USER_ID, "Europe/Berlin")

    occurrence = await pending_occurrence(session_factory, reminder_id)
    assert profile.timezone_confirmed
    assert occurrence.fire_at == datetime(2026, 10, 22, 16, 0, tzinfo=UTC)


async def test_unknown_timezone_is_rejected(service: SqlReminderService) -> None:
    with pytest.raises(ValueError, match="unknown timezone"):
        await service.set_timezone(USER_ID, "Mars/Olympus")


async def test_reminder_text_and_tags_are_not_stored(
    service: SqlReminderService, session_factory: SessionFactory, wakes: WakeCounter
) -> None:
    draft = ReminderDraft(
        text="секретный текст",
        schedule=Schedule(kind=ScheduleKind.ONCE, start=datetime(2026, 10, 22, 18, 0)),
        tags=("секретныйтег",),
        priority=Priority.CRITICAL,
        pre_offsets=(timedelta(hours=-1),),
        nagging=Nagging(interval=timedelta(minutes=10), max_repeats=6),
    )

    await service.create_reminder(USER_ID, draft)

    async with session_factory() as session:
        rows = (await session.execute(text("SELECT * FROM reminders"))).all()
    dump = repr(rows)
    assert "секретный" not in dump
    assert len(rows) == 1
    assert rows[0].payload_ct is None
    assert rows[0].priority == Priority.CRITICAL
    assert rows[0].nag_max == 6
    assert wakes.count == 1


async def test_once_reminder_appears_in_planned_fires(service: SqlReminderService) -> None:
    reminder_id = await service.create_reminder(USER_ID, once_draft(datetime(2026, 10, 22, 18, 0)))
    await service.attach_card(USER_ID, reminder_id, message_id=42)

    fires = await service.planned_fires(
        USER_ID, datetime(2026, 10, 22, tzinfo=MOSCOW), datetime(2026, 10, 23, tzinfo=MOSCOW)
    )

    assert [(fire.reminder_id, fire.at, fire.card_message_id) for fire in fires] == [
        (reminder_id, datetime(2026, 10, 22, 18, 0, tzinfo=MOSCOW), 42)
    ]
    assert fires[0].at.tzinfo == MOSCOW


async def test_recurring_reminder_is_expanded_for_a_week(service: SqlReminderService) -> None:
    await service.create_reminder(
        USER_ID, rrule_draft(datetime(2026, 10, 22, 20, 0), "FREQ=DAILY;BYHOUR=8,20;BYMINUTE=0")
    )

    fires = await service.planned_fires(
        USER_ID, datetime(2026, 10, 22, tzinfo=MOSCOW), datetime(2026, 10, 29, tzinfo=MOSCOW)
    )

    assert len(fires) == 13
    assert fires[0].at == datetime(2026, 10, 22, 20, 0, tzinfo=MOSCOW)
    assert fires[-1].at == datetime(2026, 10, 28, 20, 0, tzinfo=MOSCOW)


async def test_active_reminders_are_sorted_by_next_fire(service: SqlReminderService) -> None:
    later = await service.create_reminder(USER_ID, once_draft(datetime(2026, 10, 25, 9, 0)))
    sooner = await service.create_reminder(USER_ID, once_draft(datetime(2026, 10, 23, 9, 0)))

    summaries = await service.active_reminders(USER_ID)

    assert [summary.reminder_id for summary in summaries] == [sooner, later]
    assert summaries[0].next_fire_at == datetime(2026, 10, 23, 9, 0, tzinfo=MOSCOW)


async def test_other_users_cannot_touch_reminder(
    service: SqlReminderService, session_factory: SessionFactory
) -> None:
    reminder_id = await service.create_reminder(USER_ID, once_draft(datetime(2026, 10, 22, 18, 0)))
    occurrence = await pending_occurrence(session_factory, reminder_id)
    new_schedule = Schedule(kind=ScheduleKind.ONCE, start=datetime(2026, 10, 23, 9, 0))

    assert not await service.delete_reminder(OTHER_USER_ID, reminder_id)
    assert not await service.replace_schedule(OTHER_USER_ID, reminder_id, new_schedule)
    assert not (await service.apply_action(OTHER_USER_ID, occurrence.id, Done())).applied
    await service.attach_card(OTHER_USER_ID, reminder_id, message_id=7)
    assert await service.active_reminders(OTHER_USER_ID) == []
    assert (await service.active_reminders(USER_ID))[0].card_message_id is None


async def test_delete_removes_reminder_with_occurrences(
    service: SqlReminderService, session_factory: SessionFactory
) -> None:
    reminder_id = await service.create_reminder(USER_ID, once_draft(datetime(2026, 10, 22, 18, 0)))

    assert await service.delete_reminder(USER_ID, reminder_id)
    assert await occurrences_of(session_factory, reminder_id) == []
    assert not await service.delete_reminder(USER_ID, reminder_id)


async def test_done_finishes_once_reminder(
    service: SqlReminderService, session_factory: SessionFactory
) -> None:
    reminder_id = await service.create_reminder(USER_ID, once_draft(datetime(2026, 10, 22, 18, 0)))
    occurrence = await pending_occurrence(session_factory, reminder_id)

    outcome = await service.apply_action(USER_ID, occurrence.id, Done())

    assert outcome.applied
    assert outcome.series_finished
    assert await service.active_reminders(USER_ID) == []
    assert not (await service.apply_action(USER_ID, occurrence.id, Done())).applied


async def test_snooze_for_moves_only_this_occurrence(
    service: SqlReminderService, session_factory: SessionFactory, clock: FakeClock
) -> None:
    reminder_id = await service.create_reminder(USER_ID, once_draft(datetime(2026, 10, 22, 9, 0)))
    occurrence = await pending_occurrence(session_factory, reminder_id)

    outcome = await service.apply_action(USER_ID, occurrence.id, SnoozeFor(timedelta(minutes=15)))

    snoozed = await pending_occurrence(session_factory, reminder_id)
    assert outcome.next_fire_at == datetime(2026, 10, 22, 9, 15, tzinfo=MOSCOW)
    assert snoozed.fire_at == clock.now() + timedelta(minutes=15)
    assert snoozed.planned_at == occurrence.planned_at
    assert snoozed.snooze_count == 1


async def test_snooze_until_local_time(
    service: SqlReminderService, session_factory: SessionFactory
) -> None:
    reminder_id = await service.create_reminder(USER_ID, once_draft(datetime(2026, 10, 22, 9, 0)))
    occurrence = await pending_occurrence(session_factory, reminder_id)

    outcome = await service.apply_action(
        USER_ID, occurrence.id, SnoozeUntil(datetime(2026, 10, 23, 9, 0))
    )

    assert outcome.next_fire_at == datetime(2026, 10, 23, 9, 0, tzinfo=MOSCOW)


async def test_skip_scheduled_recurring_occurrence_plans_next(
    service: SqlReminderService, session_factory: SessionFactory
) -> None:
    reminder_id = await service.create_reminder(
        USER_ID, rrule_draft(datetime(2026, 10, 22, 20, 0), "FREQ=DAILY")
    )
    occurrence = await pending_occurrence(session_factory, reminder_id)

    outcome = await service.apply_action(USER_ID, occurrence.id, Skip())

    assert outcome.next_fire_at == datetime(2026, 10, 23, 20, 0, tzinfo=MOSCOW)
    assert not outcome.series_finished
    states = [row.state for row in await occurrences_of(session_factory, reminder_id)]
    assert states == [OccurrenceState.SKIPPED, OccurrenceState.SCHEDULED]


async def test_stop_series_completes_reminder(
    service: SqlReminderService, session_factory: SessionFactory
) -> None:
    reminder_id = await service.create_reminder(
        USER_ID, rrule_draft(datetime(2026, 10, 22, 20, 0), "FREQ=DAILY")
    )
    occurrence = await pending_occurrence(session_factory, reminder_id)

    outcome = await service.apply_action(USER_ID, occurrence.id, StopSeries())

    assert outcome.series_finished
    assert await service.active_reminders(USER_ID) == []
    states = {row.state for row in await occurrences_of(session_factory, reminder_id)}
    assert states == {OccurrenceState.CANCELLED}


async def test_done_after_completion_plans_next_from_done_time(
    service: SqlReminderService, session_factory: SessionFactory, clock: FakeClock
) -> None:
    draft = ReminderDraft(
        text="полить цветы",
        schedule=Schedule(
            kind=ScheduleKind.AFTER_COMPLETION,
            start=datetime(2026, 10, 22, 9, 0),
            interval_after_done=timedelta(days=3),
        ),
    )
    reminder_id = await service.create_reminder(USER_ID, draft)
    occurrence = await pending_occurrence(session_factory, reminder_id)
    clock.advance(timedelta(hours=2))

    outcome = await service.apply_action(USER_ID, occurrence.id, Done())

    assert outcome.next_fire_at == datetime(2026, 10, 25, 11, 0, tzinfo=MOSCOW)
    assert not outcome.series_finished


async def test_replace_schedule_cancels_pending_and_plans_new(
    service: SqlReminderService, session_factory: SessionFactory, wakes: WakeCounter
) -> None:
    reminder_id = await service.create_reminder(USER_ID, once_draft(datetime(2026, 10, 22, 18, 0)))

    replaced = await service.replace_schedule(
        USER_ID, reminder_id, Schedule(kind=ScheduleKind.ONCE, start=datetime(2026, 10, 24, 9, 0))
    )

    occurrences = await occurrences_of(session_factory, reminder_id)
    assert replaced
    assert [row.state for row in occurrences] == [
        OccurrenceState.CANCELLED,
        OccurrenceState.SCHEDULED,
    ]
    assert occurrences[1].fire_at == datetime(2026, 10, 24, 6, 0, tzinfo=UTC)
    assert wakes.count == 2


async def test_exhausted_rule_completes_reminder_immediately(service: SqlReminderService) -> None:
    await service.create_reminder(
        USER_ID, rrule_draft(datetime(2026, 10, 1, 9, 0), "FREQ=DAILY;COUNT=2")
    )

    assert await service.active_reminders(USER_ID) == []
