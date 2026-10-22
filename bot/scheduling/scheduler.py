import asyncio
import logging
from collections import defaultdict
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from bot.db.engine import SessionFactory
from bot.db.mappers import priority_of, schedule_of
from bot.db.models import (
    OccurrenceRow,
    OccurrenceState,
    ReminderRow,
    ReminderState,
    UserRow,
    UserStatus,
)
from bot.domain.occurrences import Notification, OccurrenceKind
from bot.domain.ports import Clock, Notifier, RecipientUnavailableError
from bot.domain.reminders import Priority, Schedule, ScheduleKind
from bot.scheduling.planning import advance_series
from bot.scheduling.recurrence import last_fire_between

logger = logging.getLogger(__name__)

ON_TIME_TOLERANCE = timedelta(minutes=15)
MISSED_SUMMARY_THRESHOLD = 5
UNANSWERED_TIMEOUT = timedelta(hours=24)
MAX_IDLE = timedelta(seconds=30)
RETRY_DELAY = timedelta(minutes=1)


@dataclass(frozen=True, slots=True)
class DueOccurrence:
    occurrence_id: int
    reminder_id: str
    user_id: int
    kind: OccurrenceKind
    planned_at: datetime
    fire_at: datetime
    snooze_count: int
    schedule: Schedule
    priority: Priority
    card_message_id: int | None
    timezone: ZoneInfo
    user_timezone: ZoneInfo

    def lateness(self, now: datetime) -> timedelta:
        return now - self.fire_at

    def is_overdue(self, now: datetime) -> bool:
        return self.lateness(now) > ON_TIME_TOLERANCE


class Scheduler:
    def __init__(
        self,
        session_factory: SessionFactory,
        notifier: Notifier,
        clock: Clock,
        max_idle: timedelta = MAX_IDLE,
    ) -> None:
        self._session_factory = session_factory
        self._notifier = notifier
        self._clock = clock
        self._max_idle = max_idle
        self._wake_event = asyncio.Event()

    def wake(self) -> None:
        self._wake_event.set()

    async def run(self) -> None:
        await self.recover()
        while True:
            try:
                await self.tick()
            except Exception:
                logger.exception("scheduler tick failed")
            await self._wait_for_next_fire()

    async def recover(self) -> None:
        async with self._transaction() as session:
            await session.execute(
                update(OccurrenceRow)
                .where(OccurrenceRow.state == OccurrenceState.SENDING)
                .values(state=OccurrenceState.SCHEDULED)
                .execution_options(synchronize_session=False)
            )

    async def tick(self) -> None:
        self._wake_event.clear()
        now = self._clock.now()
        await self._expire_unanswered(now)
        due_by_user: defaultdict[int, list[DueOccurrence]] = defaultdict(list)
        for due in await self._claim_due(now):
            due_by_user[due.user_id].append(due)
        for user_id, items in due_by_user.items():
            await self._dispatch_user(user_id, items, now)

    async def _dispatch_user(self, user_id: int, items: list[DueOccurrence], now: datetime) -> None:
        items = [await self._collapse_stale(item, now) for item in items]
        overdue = [item for item in items if item.is_overdue(now)]
        if len(overdue) > MISSED_SUMMARY_THRESHOLD:
            notifications = [self._notification(item, now) for item in overdue]
            try:
                await self._notifier.notify_missed(user_id, notifications)
            except RecipientUnavailableError:
                await self._mark_unavailable(user_id, items)
                return
            except Exception:
                logger.exception("missed summary failed for %d occurrences", len(overdue))
                await self._retry_later(items, now)
                return
            await self._resolve_missed(overdue, now)
            items = [item for item in items if not item.is_overdue(now)]

        ordered = sorted(items, key=lambda item: item.fire_at)
        for position, item in enumerate(ordered):
            try:
                await self._deliver(item, now)
            except RecipientUnavailableError:
                await self._mark_unavailable(user_id, ordered[position:])
                return

    async def _deliver(self, item: DueOccurrence, now: datetime) -> None:
        try:
            message_id = await self._notifier.notify(self._notification(item, now))
        except RecipientUnavailableError:
            raise
        except Exception:
            logger.exception("delivery of occurrence %d failed", item.occurrence_id)
            await self._retry_later([item], now)
            return
        await self._mark_sent(item, message_id, now)

    async def _collapse_stale(self, item: DueOccurrence, now: datetime) -> DueOccurrence:
        if (
            item.kind is not OccurrenceKind.MAIN
            or item.schedule.kind is not ScheduleKind.RRULE
            or item.snooze_count
        ):
            return item
        latest = last_fire_between(item.schedule, item.timezone, item.planned_at, now)
        if latest is None:
            return item
        async with self._transaction() as session:
            stale = await session.get(OccurrenceRow, item.occurrence_id)
            if stale is None:
                return item
            stale.state = OccurrenceState.MISSED
            fresh = OccurrenceRow(
                reminder_id=item.reminder_id,
                user_id=item.user_id,
                kind=OccurrenceKind.MAIN,
                planned_at=latest,
                fire_at=latest,
                state=OccurrenceState.SENDING,
            )
            session.add(fresh)
            await session.flush()
        return replace(item, occurrence_id=fresh.id, planned_at=latest, fire_at=latest)

    async def _mark_sent(self, item: DueOccurrence, message_id: int, now: datetime) -> None:
        async with self._transaction() as session:
            occurrence = await session.get(OccurrenceRow, item.occurrence_id)
            if occurrence is None:
                return
            occurrence.state = OccurrenceState.SENT
            occurrence.sent_message_id = message_id
            occurrence.sent_at = now
            await session.execute(
                update(OccurrenceRow)
                .where(
                    OccurrenceRow.reminder_id == item.reminder_id,
                    OccurrenceRow.kind == OccurrenceKind.MAIN,
                    OccurrenceRow.state == OccurrenceState.SENT,
                    OccurrenceRow.id != item.occurrence_id,
                )
                .values(state=OccurrenceState.MISSED)
                .execution_options(synchronize_session=False)
            )
            if item.kind is OccurrenceKind.MAIN and item.schedule.kind is ScheduleKind.RRULE:
                reminder = await session.get(ReminderRow, item.reminder_id)
                if reminder is not None and reminder.state is ReminderState.ACTIVE:
                    await advance_series(session, reminder, item.timezone, item.planned_at, now)

    async def _resolve_missed(self, items: Sequence[DueOccurrence], now: datetime) -> None:
        async with self._transaction() as session:
            for item in items:
                occurrence = await session.get(OccurrenceRow, item.occurrence_id)
                if occurrence is None:
                    continue
                occurrence.state = OccurrenceState.MISSED
                await session.flush()
                reminder = await session.get(ReminderRow, item.reminder_id)
                if reminder is not None and reminder.state is ReminderState.ACTIVE:
                    await advance_series(session, reminder, item.timezone, item.planned_at, now)

    async def _expire_unanswered(self, now: datetime) -> None:
        async with self._transaction() as session:
            expired = await session.scalars(
                select(OccurrenceRow)
                .options(joinedload(OccurrenceRow.reminder).joinedload(ReminderRow.user))
                .where(
                    OccurrenceRow.state == OccurrenceState.SENT,
                    OccurrenceRow.sent_at < now - UNANSWERED_TIMEOUT,
                )
            )
            for occurrence in list(expired):
                occurrence.state = OccurrenceState.MISSED
                await session.flush()
                reminder = occurrence.reminder
                if reminder.state is ReminderState.ACTIVE:
                    tz = ZoneInfo(reminder.tz or reminder.user.timezone)
                    await advance_series(session, reminder, tz, occurrence.planned_at, now)

    async def _claim_due(self, now: datetime) -> list[DueOccurrence]:
        active_users = select(UserRow.id).where(UserRow.status == UserStatus.ACTIVE)
        async with self._transaction() as session:
            claimed = list(
                await session.scalars(
                    update(OccurrenceRow)
                    .where(
                        OccurrenceRow.state == OccurrenceState.SCHEDULED,
                        OccurrenceRow.fire_at <= now,
                        OccurrenceRow.user_id.in_(active_users),
                    )
                    .values(state=OccurrenceState.SENDING)
                    .returning(OccurrenceRow.id)
                    .execution_options(synchronize_session=False)
                )
            )
            if not claimed:
                return []
            rows = await session.scalars(
                select(OccurrenceRow)
                .options(joinedload(OccurrenceRow.reminder).joinedload(ReminderRow.user))
                .where(OccurrenceRow.id.in_(claimed))
                .order_by(OccurrenceRow.fire_at)
            )
            return [self._due_from(row) for row in rows]

    async def _mark_unavailable(self, user_id: int, items: Sequence[DueOccurrence]) -> None:
        logger.info("recipient unavailable, pausing delivery")
        async with self._transaction() as session:
            await session.execute(
                update(UserRow).where(UserRow.id == user_id).values(status=UserStatus.BLOCKED)
            )
            await self._reschedule(session, items)

    async def _retry_later(self, items: Sequence[DueOccurrence], now: datetime) -> None:
        async with self._transaction() as session:
            await self._reschedule(session, items, now + RETRY_DELAY)

    async def _reschedule(
        self,
        session: AsyncSession,
        items: Sequence[DueOccurrence],
        fire_at: datetime | None = None,
    ) -> None:
        values: dict[str, object] = {"state": OccurrenceState.SCHEDULED}
        if fire_at is not None:
            values["fire_at"] = fire_at
        await session.execute(
            update(OccurrenceRow)
            .where(
                OccurrenceRow.id.in_([item.occurrence_id for item in items]),
                OccurrenceRow.state == OccurrenceState.SENDING,
            )
            .values(values)
            .execution_options(synchronize_session=False)
        )

    async def _wait_for_next_fire(self) -> None:
        with suppress(TimeoutError):
            await asyncio.wait_for(
                self._wake_event.wait(), timeout=await self.seconds_until_next_fire()
            )

    async def seconds_until_next_fire(self) -> float:
        async with self._session_factory() as session:
            next_fire = await session.scalar(
                select(func.min(OccurrenceRow.fire_at))
                .join(UserRow, UserRow.id == OccurrenceRow.user_id)
                .where(
                    OccurrenceRow.state == OccurrenceState.SCHEDULED,
                    UserRow.status == UserStatus.ACTIVE,
                )
            )
        max_idle = self._max_idle.total_seconds()
        if next_fire is None:
            return max_idle
        return min(max(0.0, (next_fire - self._clock.now()).total_seconds()), max_idle)

    @asynccontextmanager
    async def _transaction(self) -> AsyncIterator[AsyncSession]:
        async with self._session_factory() as session, session.begin():
            yield session

    @staticmethod
    def _due_from(occurrence: OccurrenceRow) -> DueOccurrence:
        reminder = occurrence.reminder
        user_timezone = ZoneInfo(reminder.user.timezone)
        return DueOccurrence(
            occurrence_id=occurrence.id,
            reminder_id=reminder.id,
            user_id=occurrence.user_id,
            kind=occurrence.kind,
            planned_at=occurrence.planned_at,
            fire_at=occurrence.fire_at,
            snooze_count=occurrence.snooze_count,
            schedule=schedule_of(reminder),
            priority=priority_of(reminder),
            card_message_id=reminder.card_message_id,
            timezone=ZoneInfo(reminder.tz) if reminder.tz else user_timezone,
            user_timezone=user_timezone,
        )

    @staticmethod
    def _notification(item: DueOccurrence, now: datetime) -> Notification:
        lateness = item.lateness(now)
        return Notification(
            occurrence_id=item.occurrence_id,
            reminder_id=item.reminder_id,
            user_id=item.user_id,
            kind=item.kind,
            card_message_id=item.card_message_id,
            schedule=item.schedule,
            priority=item.priority,
            planned_at=item.planned_at.astimezone(item.user_timezone),
            overdue_by=lateness if lateness > ON_TIME_TOLERANCE else timedelta(0),
        )
