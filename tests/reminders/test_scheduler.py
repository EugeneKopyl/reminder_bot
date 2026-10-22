from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import update

from bot.db.engine import SessionFactory
from bot.db.models import OccurrenceRow, OccurrenceState, UserRow, UserStatus
from bot.domain.occurrences import Done, OccurrenceKind
from bot.domain.reminders import ReminderDraft, Schedule, ScheduleKind
from bot.scheduling.scheduler import Scheduler
from bot.services.reminders import SqlReminderService
from tests.reminders.conftest import (
    USER_ID,
    FakeClock,
    FakeNotifier,
    occurrences_of,
    once_draft,
    pending_occurrence,
    rrule_draft,
)

MOSCOW = ZoneInfo("Europe/Moscow")


async def test_due_occurrence_is_delivered(
    service: SqlReminderService,
    scheduler: Scheduler,
    notifier: FakeNotifier,
    session_factory: SessionFactory,
) -> None:
    reminder_id = await service.create_reminder(USER_ID, once_draft(datetime(2026, 10, 22, 9, 0)))
    await service.attach_card(USER_ID, reminder_id, message_id=42)

    await scheduler.tick()

    [notification] = notifier.sent
    assert notification.reminder_id == reminder_id
    assert notification.kind is OccurrenceKind.MAIN
    assert notification.card_message_id == 42
    assert notification.planned_at == datetime(2026, 10, 22, 9, 0, tzinfo=MOSCOW)
    assert notification.overdue_by == timedelta(0)
    [occurrence] = await occurrences_of(session_factory, reminder_id)
    assert occurrence.state is OccurrenceState.SENT
    assert occurrence.sent_message_id == 501


async def test_future_occurrence_is_not_delivered(
    service: SqlReminderService, scheduler: Scheduler, notifier: FakeNotifier
) -> None:
    await service.create_reminder(USER_ID, once_draft(datetime(2026, 10, 22, 9, 1)))

    await scheduler.tick()

    assert notifier.sent == []
    assert await scheduler.seconds_until_next_fire() == 30


async def test_seconds_until_next_fire_counts_down(
    service: SqlReminderService, scheduler: Scheduler
) -> None:
    await service.create_reminder(USER_ID, once_draft(datetime(2026, 10, 22, 9, 0, 10)))

    assert await scheduler.seconds_until_next_fire() == 10


async def test_recurring_delivery_plans_next_and_marks_previous_missed(
    service: SqlReminderService,
    scheduler: Scheduler,
    notifier: FakeNotifier,
    session_factory: SessionFactory,
    clock: FakeClock,
) -> None:
    reminder_id = await service.create_reminder(
        USER_ID, rrule_draft(datetime(2026, 10, 22, 9, 0), "FREQ=HOURLY")
    )

    await scheduler.tick()
    clock.advance(timedelta(hours=1))
    await scheduler.tick()

    states = [row.state for row in await occurrences_of(session_factory, reminder_id)]
    assert states == [OccurrenceState.MISSED, OccurrenceState.SENT, OccurrenceState.SCHEDULED]
    assert len(notifier.sent) == 2


async def test_done_after_delivery_keeps_planned_next_occurrence(
    service: SqlReminderService,
    scheduler: Scheduler,
    notifier: FakeNotifier,
    session_factory: SessionFactory,
) -> None:
    reminder_id = await service.create_reminder(
        USER_ID, rrule_draft(datetime(2026, 10, 22, 9, 0), "FREQ=DAILY")
    )
    await scheduler.tick()

    outcome = await service.apply_action(USER_ID, notifier.sent[0].occurrence_id, Done())

    assert outcome.next_fire_at == datetime(2026, 10, 23, 9, 0, tzinfo=MOSCOW)
    states = [row.state for row in await occurrences_of(session_factory, reminder_id)]
    assert states == [OccurrenceState.DONE, OccurrenceState.SCHEDULED]


async def test_unanswered_once_reminder_expires_after_a_day(
    service: SqlReminderService,
    scheduler: Scheduler,
    session_factory: SessionFactory,
    clock: FakeClock,
) -> None:
    reminder_id = await service.create_reminder(USER_ID, once_draft(datetime(2026, 10, 22, 9, 0)))
    await scheduler.tick()

    clock.advance(timedelta(hours=25))
    await scheduler.tick()

    [occurrence] = await occurrences_of(session_factory, reminder_id)
    assert occurrence.state is OccurrenceState.MISSED
    assert await service.active_reminders(USER_ID) == []


async def test_slightly_late_occurrence_is_sent_as_usual(
    service: SqlReminderService, scheduler: Scheduler, notifier: FakeNotifier, clock: FakeClock
) -> None:
    await service.create_reminder(USER_ID, once_draft(datetime(2026, 10, 22, 9, 0)))
    clock.advance(timedelta(minutes=10))

    await scheduler.tick()

    assert notifier.sent[0].overdue_by == timedelta(0)


async def test_overdue_occurrence_reports_delay(
    service: SqlReminderService, scheduler: Scheduler, notifier: FakeNotifier, clock: FakeClock
) -> None:
    await service.create_reminder(USER_ID, once_draft(datetime(2026, 10, 22, 9, 0)))
    clock.advance(timedelta(hours=2))

    await scheduler.tick()

    assert notifier.sent[0].overdue_by == timedelta(hours=2)


async def test_many_overdue_occurrences_are_summarized(
    service: SqlReminderService,
    scheduler: Scheduler,
    notifier: FakeNotifier,
    session_factory: SessionFactory,
    clock: FakeClock,
) -> None:
    reminder_ids = [
        await service.create_reminder(USER_ID, once_draft(datetime(2026, 10, 22, 9, minute)))
        for minute in range(6)
    ]
    on_time_id = await service.create_reminder(USER_ID, once_draft(datetime(2026, 10, 22, 12, 0)))
    clock.advance(timedelta(hours=3))

    await scheduler.tick()

    [(user_id, missed)] = notifier.missed
    assert user_id == USER_ID
    assert {notification.reminder_id for notification in missed} == set(reminder_ids)
    assert [notification.reminder_id for notification in notifier.sent] == [on_time_id]
    for reminder_id in reminder_ids:
        [occurrence] = await occurrences_of(session_factory, reminder_id)
        assert occurrence.state is OccurrenceState.MISSED


async def test_recurring_reminder_sends_only_latest_missed_fire(
    service: SqlReminderService,
    scheduler: Scheduler,
    notifier: FakeNotifier,
    session_factory: SessionFactory,
    clock: FakeClock,
) -> None:
    reminder_id = await service.create_reminder(
        USER_ID, rrule_draft(datetime(2026, 10, 22, 9, 0), "FREQ=DAILY")
    )
    clock.advance(timedelta(days=3, hours=1))

    await scheduler.tick()

    [notification] = notifier.sent
    assert notification.planned_at == datetime(2026, 10, 25, 9, 0, tzinfo=MOSCOW)
    assert notification.overdue_by == timedelta(hours=1)
    occurrences = await occurrences_of(session_factory, reminder_id)
    assert [row.state for row in occurrences] == [
        OccurrenceState.MISSED,
        OccurrenceState.SENT,
        OccurrenceState.SCHEDULED,
    ]
    assert occurrences[-1].fire_at == datetime(2026, 10, 26, 6, 0, tzinfo=UTC)


async def test_stuck_sending_occurrence_is_resent_after_restart(
    service: SqlReminderService,
    scheduler: Scheduler,
    notifier: FakeNotifier,
    session_factory: SessionFactory,
) -> None:
    reminder_id = await service.create_reminder(USER_ID, once_draft(datetime(2026, 10, 22, 9, 0)))
    async with session_factory() as session, session.begin():
        await session.execute(
            update(OccurrenceRow)
            .where(OccurrenceRow.reminder_id == reminder_id)
            .values(state=OccurrenceState.SENDING)
        )

    await scheduler.recover()
    await scheduler.tick()

    assert [notification.reminder_id for notification in notifier.sent] == [reminder_id]


async def test_blocked_user_is_paused_until_return(
    service: SqlReminderService,
    scheduler: Scheduler,
    notifier: FakeNotifier,
    session_factory: SessionFactory,
    clock: FakeClock,
) -> None:
    reminder_id = await service.create_reminder(USER_ID, once_draft(datetime(2026, 10, 22, 9, 0)))
    notifier.unavailable_users.add(USER_ID)

    await scheduler.tick()

    async with session_factory() as session:
        user = await session.get_one(UserRow, USER_ID)
    assert user.status is UserStatus.BLOCKED
    assert (await pending_occurrence(session_factory, reminder_id)).state is (
        OccurrenceState.SCHEDULED
    )

    notifier.unavailable_users.clear()
    clock.advance(timedelta(minutes=5))
    await scheduler.tick()
    assert notifier.sent == []

    await service.ensure_user(USER_ID)
    await scheduler.tick()
    assert [notification.reminder_id for notification in notifier.sent] == [reminder_id]


async def test_failed_delivery_is_retried_later(
    service: SqlReminderService,
    scheduler: Scheduler,
    notifier: FakeNotifier,
    session_factory: SessionFactory,
    clock: FakeClock,
) -> None:
    reminder_id = await service.create_reminder(USER_ID, once_draft(datetime(2026, 10, 22, 9, 0)))
    notifier.failing = True

    await scheduler.tick()

    occurrence = await pending_occurrence(session_factory, reminder_id)
    assert occurrence.fire_at == clock.now() + timedelta(minutes=1)

    notifier.failing = False
    clock.advance(timedelta(minutes=1))
    await scheduler.tick()
    assert len(notifier.sent) == 1


async def test_after_completion_reminder_continues_when_unanswered(
    service: SqlReminderService,
    scheduler: Scheduler,
    session_factory: SessionFactory,
    clock: FakeClock,
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
    await scheduler.tick()

    clock.advance(timedelta(hours=25))
    await scheduler.tick()

    occurrences = await occurrences_of(session_factory, reminder_id)
    assert [row.state for row in occurrences] == [OccurrenceState.MISSED, OccurrenceState.SCHEDULED]
    assert occurrences[1].fire_at == clock.now() + timedelta(days=3)


async def test_wake_interrupts_idle_wait(scheduler: Scheduler) -> None:
    scheduler.wake()

    await scheduler._wait_for_next_fire()
