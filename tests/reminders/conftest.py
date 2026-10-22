import shutil
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from bot.db.engine import SessionFactory, create_engine, create_session_factory
from bot.db.models import OccurrenceRow, OccurrenceState
from bot.db.schema import upgrade_database
from bot.domain.occurrences import Notification
from bot.domain.ports import RecipientUnavailableError
from bot.domain.reminders import ReminderDraft, Schedule, ScheduleKind
from bot.scheduling.scheduler import Scheduler
from bot.services.reminders import SqlReminderService

USER_ID = 1001
OTHER_USER_ID = 2002
DEFAULT_TIMEZONE = "Europe/Moscow"
START = datetime(2026, 10, 22, 6, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.current = now

    def now(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


class FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[Notification] = []
        self.missed: list[tuple[int, list[Notification]]] = []
        self.unavailable_users: set[int] = set()
        self.failing = False
        self._message_id = 500

    async def notify(self, notification: Notification) -> int:
        if notification.user_id in self.unavailable_users:
            raise RecipientUnavailableError
        if self.failing:
            raise RuntimeError("telegram is down")
        self.sent.append(notification)
        self._message_id += 1
        return self._message_id

    async def notify_missed(self, user_id: int, notifications: Sequence[Notification]) -> None:
        if user_id in self.unavailable_users:
            raise RecipientUnavailableError
        self.missed.append((user_id, list(notifications)))


class WakeCounter:
    def __init__(self) -> None:
        self.count = 0

    def __call__(self) -> None:
        self.count += 1


def once_draft(start: datetime, text: str = "позвонить маме") -> ReminderDraft:
    return ReminderDraft(text=text, schedule=Schedule(kind=ScheduleKind.ONCE, start=start))


def rrule_draft(start: datetime, rule: str, text: str = "таблетки") -> ReminderDraft:
    return ReminderDraft(
        text=text, schedule=Schedule(kind=ScheduleKind.RRULE, start=start, rrule=rule)
    )


async def occurrences_of(session_factory: SessionFactory, reminder_id: str) -> list[OccurrenceRow]:
    async with session_factory() as session:
        result = await session.scalars(
            select(OccurrenceRow)
            .where(OccurrenceRow.reminder_id == reminder_id)
            .order_by(OccurrenceRow.id)
        )
        return list(result)


async def pending_occurrence(session_factory: SessionFactory, reminder_id: str) -> OccurrenceRow:
    occurrences = await occurrences_of(session_factory, reminder_id)
    return next(row for row in occurrences if row.state is OccurrenceState.SCHEDULED)


@pytest.fixture(scope="session")
def migrated_database(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("template") / "template.sqlite3"
    upgrade_database(path)
    return path


@pytest.fixture
async def session_factory(migrated_database: Path, tmp_path: Path) -> AsyncIterator[SessionFactory]:
    database_path = tmp_path / "bot.sqlite3"
    shutil.copyfile(migrated_database, database_path)
    engine = create_engine(database_path)
    yield create_session_factory(engine)
    await engine.dispose()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(START)


@pytest.fixture
def notifier() -> FakeNotifier:
    return FakeNotifier()


@pytest.fixture
def wakes() -> WakeCounter:
    return WakeCounter()


@pytest.fixture
def service(
    session_factory: SessionFactory, clock: FakeClock, wakes: WakeCounter
) -> SqlReminderService:
    return SqlReminderService(session_factory, clock, DEFAULT_TIMEZONE, on_schedule_change=wakes)


@pytest.fixture
def scheduler(
    session_factory: SessionFactory, notifier: FakeNotifier, clock: FakeClock
) -> Scheduler:
    return Scheduler(session_factory, notifier, clock)
