from collections import defaultdict
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo, available_timezones

from sqlalchemy import delete, or_, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from bot.db.engine import SessionFactory
from bot.db.mappers import apply_schedule, priority_of, profile_of, schedule_of
from bot.db.models import (
    PENDING_STATES,
    OccurrenceRow,
    OccurrenceState,
    ReminderRow,
    ReminderSource,
    ReminderState,
    UserRow,
    UserStatus,
    new_reminder_id,
)
from bot.domain.occurrences import (
    ActionOutcome,
    Done,
    OccurrenceAction,
    OccurrenceKind,
    PlannedFire,
    ReminderSummary,
    Skip,
    SnoozeFor,
    SnoozeUntil,
    StopSeries,
)
from bot.domain.ports import Clock
from bot.domain.reminders import ReminderDraft, Schedule, ScheduleKind, UserProfile
from bot.scheduling.planning import advance_series, first_fire, new_main_occurrence
from bot.scheduling.recurrence import fires_between, to_local, to_utc

ACTIONABLE_STATES = (OccurrenceState.SCHEDULED, OccurrenceState.SENT, OccurrenceState.MISSED)
VISIBLE_STATES = (*PENDING_STATES, OccurrenceState.SENT)


class SqlReminderService:
    def __init__(
        self,
        session_factory: SessionFactory,
        clock: Clock,
        default_timezone: str,
        on_schedule_change: Callable[[], None] = lambda: None,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._default_timezone = default_timezone
        self._on_schedule_change = on_schedule_change

    async def ensure_user(self, user_id: int) -> UserProfile:
        async with self._transaction() as session:
            user = await self._user(session, user_id)
            reactivated = user.status is UserStatus.BLOCKED
            if reactivated:
                user.status = UserStatus.ACTIVE
            profile = profile_of(user)
        if reactivated:
            self._on_schedule_change()
        return profile

    async def set_timezone(self, user_id: int, timezone: str) -> UserProfile:
        if timezone not in available_timezones():
            raise ValueError(f"unknown timezone: {timezone}")
        async with self._transaction() as session:
            user = await self._user(session, user_id)
            previous = ZoneInfo(user.timezone)
            user.timezone = timezone
            user.timezone_confirmed = True
            await self._shift_floating_occurrences(session, user_id, previous, ZoneInfo(timezone))
            profile = profile_of(user)
        self._on_schedule_change()
        return profile

    async def create_reminder(self, user_id: int, draft: ReminderDraft) -> str:
        now = self._clock.now()
        async with self._transaction() as session:
            user = await self._user(session, user_id)
            reminder = ReminderRow(
                id=new_reminder_id(),
                user_id=user_id,
                priority=int(draft.priority),
                pre_offsets=list(draft.pre_offsets),
                nag_interval=draft.nagging.interval if draft.nagging else None,
                nag_max=draft.nagging.max_repeats if draft.nagging else None,
                source=ReminderSource.CHAT,
                created_at=now,
                updated_at=now,
            )
            apply_schedule(reminder, draft.schedule)
            session.add(reminder)
            self._plan_first_occurrence(session, reminder, ZoneInfo(user.timezone), now)
        self._on_schedule_change()
        return reminder.id

    async def attach_card(self, user_id: int, reminder_id: str, message_id: int) -> None:
        async with self._transaction() as session:
            await session.execute(
                update(ReminderRow)
                .where(ReminderRow.id == reminder_id, ReminderRow.user_id == user_id)
                .values(card_message_id=message_id, updated_at=self._clock.now())
            )

    async def replace_schedule(self, user_id: int, reminder_id: str, schedule: Schedule) -> bool:
        now = self._clock.now()
        async with self._transaction() as session:
            reminder = await self._owned_reminder(session, user_id, reminder_id)
            if reminder is None:
                return False
            apply_schedule(reminder, schedule)
            reminder.state = ReminderState.ACTIVE
            reminder.updated_at = now
            await self._cancel_pending(session, reminder_id)
            self._plan_first_occurrence(session, reminder, self._timezone_of(reminder), now)
        self._on_schedule_change()
        return True

    async def delete_reminder(self, user_id: int, reminder_id: str) -> bool:
        async with self._transaction() as session:
            deleted_id = await session.scalar(
                delete(ReminderRow)
                .where(ReminderRow.id == reminder_id, ReminderRow.user_id == user_id)
                .returning(ReminderRow.id)
            )
        return deleted_id is not None

    async def apply_action(
        self, user_id: int, occurrence_id: int, action: OccurrenceAction
    ) -> ActionOutcome:
        now = self._clock.now()
        async with self._transaction() as session:
            occurrence = await session.scalar(
                select(OccurrenceRow)
                .options(joinedload(OccurrenceRow.reminder).joinedload(ReminderRow.user))
                .where(OccurrenceRow.id == occurrence_id, OccurrenceRow.user_id == user_id)
            )
            if occurrence is None or occurrence.state not in ACTIONABLE_STATES:
                return ActionOutcome(applied=False)
            outcome = await self._apply(session, occurrence, action, now)
        self._on_schedule_change()
        return outcome

    async def planned_fires(
        self, user_id: int, start: datetime, end: datetime
    ) -> list[PlannedFire]:
        now = self._clock.now()
        async with self._session_factory() as session:
            user = await session.get(UserRow, user_id)
            if user is None:
                return []
            reminders = await self._active_reminders(session, user_id)
            occurrences_by_reminder = await self._occurrences_in_range(
                session, [reminder.id for reminder in reminders], start, end
            )

        user_tz = ZoneInfo(user.timezone)
        fires: list[PlannedFire] = []
        for reminder in reminders:
            occurrences = occurrences_by_reminder[reminder.id]
            fires.extend(
                self._planned_fire(reminder, occurrence.fire_at, user_tz)
                for occurrence in occurrences
                if occurrence.state in VISIBLE_STATES and start <= occurrence.fire_at < end
            )
            if reminder.kind is ScheduleKind.RRULE:
                consumed = {occurrence.planned_at for occurrence in occurrences}
                tz = ZoneInfo(reminder.tz or user.timezone)
                fires.extend(
                    self._planned_fire(reminder, fire, user_tz)
                    for fire in fires_between(schedule_of(reminder), tz, max(start, now), end)
                    if fire not in consumed
                )
        return sorted(fires, key=lambda fire: fire.at)

    async def active_reminders(self, user_id: int) -> list[ReminderSummary]:
        async with self._session_factory() as session:
            user = await session.get(UserRow, user_id)
            if user is None:
                return []
            reminders = await self._active_reminders(session, user_id)
            next_fires = await self._next_pending_fires(session, user_id)

        user_tz = ZoneInfo(user.timezone)
        summaries = [
            ReminderSummary(
                reminder_id=reminder.id,
                schedule=schedule_of(reminder),
                priority=priority_of(reminder),
                next_fire_at=_in_tz(next_fires.get(reminder.id), user_tz),
                card_message_id=reminder.card_message_id,
            )
            for reminder in reminders
        ]
        return sorted(summaries, key=_by_next_fire)

    @asynccontextmanager
    async def _transaction(self) -> AsyncIterator[AsyncSession]:
        async with self._session_factory() as session, session.begin():
            yield session

    async def _user(self, session: AsyncSession, user_id: int) -> UserRow:
        now = self._clock.now()
        await session.execute(
            insert(UserRow)
            .values(
                id=user_id,
                timezone=self._default_timezone,
                timezone_confirmed=False,
                key_version=0,
                privacy_mode="standard",
                settings={},
                status=UserStatus.ACTIVE.value,
                created_at=now,
            )
            .on_conflict_do_nothing(index_elements=[UserRow.id])
        )
        user = await session.get_one(UserRow, user_id)
        user.last_active_on = now.date()
        return user

    async def _owned_reminder(
        self, session: AsyncSession, user_id: int, reminder_id: str
    ) -> ReminderRow | None:
        return await session.scalar(
            select(ReminderRow)
            .options(joinedload(ReminderRow.user))
            .where(ReminderRow.id == reminder_id, ReminderRow.user_id == user_id)
        )

    async def _active_reminders(self, session: AsyncSession, user_id: int) -> list[ReminderRow]:
        result = await session.scalars(
            select(ReminderRow).where(
                ReminderRow.user_id == user_id, ReminderRow.state == ReminderState.ACTIVE
            )
        )
        return list(result)

    async def _occurrences_in_range(
        self, session: AsyncSession, reminder_ids: list[str], start: datetime, end: datetime
    ) -> defaultdict[str, list[OccurrenceRow]]:
        result = await session.scalars(
            select(OccurrenceRow).where(
                OccurrenceRow.reminder_id.in_(reminder_ids),
                OccurrenceRow.kind == OccurrenceKind.MAIN,
                or_(
                    OccurrenceRow.fire_at.between(start, end),
                    OccurrenceRow.planned_at.between(start, end),
                ),
            )
        )
        grouped: defaultdict[str, list[OccurrenceRow]] = defaultdict(list)
        for occurrence in result:
            grouped[occurrence.reminder_id].append(occurrence)
        return grouped

    async def _next_pending_fires(self, session: AsyncSession, user_id: int) -> dict[str, datetime]:
        result = await session.scalars(
            select(OccurrenceRow).where(
                OccurrenceRow.user_id == user_id,
                OccurrenceRow.kind == OccurrenceKind.MAIN,
                OccurrenceRow.state.in_(PENDING_STATES),
            )
        )
        next_fires: dict[str, datetime] = {}
        for occurrence in result:
            current = next_fires.get(occurrence.reminder_id)
            if current is None or occurrence.fire_at < current:
                next_fires[occurrence.reminder_id] = occurrence.fire_at
        return next_fires

    async def _shift_floating_occurrences(
        self, session: AsyncSession, user_id: int, previous: ZoneInfo, current: ZoneInfo
    ) -> None:
        result = await session.scalars(
            select(OccurrenceRow)
            .join(OccurrenceRow.reminder)
            .where(
                OccurrenceRow.user_id == user_id,
                OccurrenceRow.state == OccurrenceState.SCHEDULED,
                OccurrenceRow.snooze_count == 0,
                ReminderRow.tz.is_(None),
            )
        )
        for occurrence in result:
            shifted = to_utc(to_local(occurrence.planned_at, previous), current)
            occurrence.planned_at = shifted
            occurrence.fire_at = shifted

    async def _cancel_pending(self, session: AsyncSession, reminder_id: str) -> None:
        await session.execute(
            update(OccurrenceRow)
            .where(
                OccurrenceRow.reminder_id == reminder_id,
                OccurrenceRow.state.in_(PENDING_STATES),
            )
            .values(state=OccurrenceState.CANCELLED)
            .execution_options(synchronize_session=False)
        )

    def _plan_first_occurrence(
        self, session: AsyncSession, reminder: ReminderRow, tz: ZoneInfo, now: datetime
    ) -> None:
        fire = first_fire(schedule_of(reminder), tz, now)
        if fire is None:
            reminder.state = ReminderState.COMPLETED
        else:
            session.add(new_main_occurrence(reminder, fire))

    async def _apply(
        self,
        session: AsyncSession,
        occurrence: OccurrenceRow,
        action: OccurrenceAction,
        now: datetime,
    ) -> ActionOutcome:
        reminder = occurrence.reminder
        tz = self._timezone_of(reminder)
        user_tz = ZoneInfo(reminder.user.timezone)
        match action:
            case Done():
                occurrence.state = OccurrenceState.DONE
                occurrence.done_at = now
                return await self._advance(session, occurrence, tz, user_tz, now)
            case Skip():
                occurrence.state = OccurrenceState.SKIPPED
                return await self._advance(session, occurrence, tz, user_tz, now)
            case SnoozeFor(delta=delta):
                return self._snooze(occurrence, now + delta, user_tz)
            case SnoozeUntil(local_time=local_time):
                until = to_utc(local_time, user_tz) if local_time.tzinfo is None else local_time
                return self._snooze(occurrence, until, user_tz)
            case StopSeries():
                if occurrence.state is OccurrenceState.SCHEDULED:
                    occurrence.state = OccurrenceState.CANCELLED
                await self._cancel_pending(session, reminder.id)
                reminder.state = ReminderState.COMPLETED
                reminder.updated_at = now
                return ActionOutcome(applied=True, series_finished=True)

    async def _advance(
        self,
        session: AsyncSession,
        occurrence: OccurrenceRow,
        tz: ZoneInfo,
        user_tz: ZoneInfo,
        now: datetime,
    ) -> ActionOutcome:
        await session.flush()
        next_fire = await advance_series(
            session, occurrence.reminder, tz, occurrence.planned_at, now
        )
        return ActionOutcome(
            applied=True,
            next_fire_at=_in_tz(next_fire, user_tz),
            series_finished=next_fire is None,
        )

    def _snooze(
        self, occurrence: OccurrenceRow, until: datetime, user_tz: ZoneInfo
    ) -> ActionOutcome:
        occurrence.state = OccurrenceState.SCHEDULED
        occurrence.fire_at = until
        occurrence.snooze_count += 1
        return ActionOutcome(applied=True, next_fire_at=until.astimezone(user_tz))

    def _planned_fire(self, reminder: ReminderRow, at: datetime, user_tz: ZoneInfo) -> PlannedFire:
        return PlannedFire(
            reminder_id=reminder.id,
            at=at.astimezone(user_tz),
            schedule=schedule_of(reminder),
            priority=priority_of(reminder),
            card_message_id=reminder.card_message_id,
        )

    @staticmethod
    def _timezone_of(reminder: ReminderRow) -> ZoneInfo:
        return ZoneInfo(reminder.tz or reminder.user.timezone)


def _in_tz(instant: datetime | None, tz: ZoneInfo) -> datetime | None:
    return None if instant is None else instant.astimezone(tz)


def _by_next_fire(summary: ReminderSummary) -> tuple[bool, float]:
    if summary.next_fire_at is None:
        return True, 0.0
    return False, summary.next_fire_at.timestamp()
