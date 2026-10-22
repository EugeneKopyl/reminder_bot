from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, User

from bot.domain.occurrences import (
    ActionOutcome,
    OccurrenceAction,
    PlannedFire,
    ReminderSummary,
)
from bot.domain.parsing import ParseResult, ReminderParser
from bot.domain.reminders import DayPeriodDefaults, ReminderDraft, Schedule, UserProfile

USER_ID = 1
NOW_UTC = datetime(2026, 10, 22, 6, 0, tzinfo=UTC)


@dataclass
class FixedClock:
    moment: datetime = NOW_UTC

    def now(self) -> datetime:
        return self.moment


@dataclass
class FakeReminderService:
    profile: UserProfile = field(
        default_factory=lambda: UserProfile(USER_ID, "Europe/Moscow", True, DayPeriodDefaults())
    )
    outcome: ActionOutcome = field(default_factory=lambda: ActionOutcome(applied=True))
    fires: list[PlannedFire] = field(default_factory=list)
    summaries: list[ReminderSummary] = field(default_factory=list)
    created: list[ReminderDraft] = field(default_factory=list)
    cards: dict[str, int] = field(default_factory=dict)
    replaced: list[tuple[str, Schedule]] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    actions: list[tuple[int, OccurrenceAction]] = field(default_factory=list)
    fire_windows: list[tuple[datetime, datetime]] = field(default_factory=list)

    async def ensure_user(self, user_id: int) -> UserProfile:
        return replace(self.profile, user_id=user_id)

    async def set_timezone(self, user_id: int, timezone: str) -> UserProfile:
        self.profile = replace(self.profile, timezone=timezone, timezone_confirmed=True)
        return self.profile

    async def create_reminder(self, user_id: int, draft: ReminderDraft) -> str:
        self.created.append(draft)
        return f"reminder-{len(self.created)}"

    async def attach_card(self, user_id: int, reminder_id: str, message_id: int) -> None:
        self.cards[reminder_id] = message_id

    async def replace_schedule(self, user_id: int, reminder_id: str, schedule: Schedule) -> bool:
        self.replaced.append((reminder_id, schedule))
        return True

    async def delete_reminder(self, user_id: int, reminder_id: str) -> bool:
        self.deleted.append(reminder_id)
        return True

    async def apply_action(
        self, user_id: int, occurrence_id: int, action: OccurrenceAction
    ) -> ActionOutcome:
        self.actions.append((occurrence_id, action))
        return self.outcome

    async def planned_fires(
        self, user_id: int, start: datetime, end: datetime
    ) -> list[PlannedFire]:
        self.fire_windows.append((start, end))
        return self.fires

    async def active_reminders(self, user_id: int) -> list[ReminderSummary]:
        return self.summaries


def parser_returning(result: ParseResult) -> ReminderParser:
    def parse(text: str, now: datetime, day_periods: DayPeriodDefaults) -> ParseResult:
        return result

    return parse


def make_bot(sent_message_id: int = 100) -> AsyncMock:
    bot = AsyncMock()
    bot.id = 42
    bot.send_message.return_value = SimpleNamespace(message_id=sent_message_id)
    return bot


def make_state() -> FSMContext:
    key = StorageKey(bot_id=42, chat_id=USER_ID, user_id=USER_ID)
    return FSMContext(storage=MemoryStorage(), key=key)


def make_user() -> User:
    return User(id=USER_ID, is_bot=False, first_name="Test")


def make_message(text: str | None = "text", message_id: int = 10) -> Message:
    return Message(
        message_id=message_id,
        date=NOW_UTC,
        chat=Chat(id=USER_ID, type="private"),
        from_user=make_user(),
        text=text,
    )


def make_callback(data: str, message_id: int = 50) -> CallbackQuery:
    return CallbackQuery(
        id="callback",
        from_user=make_user(),
        chat_instance="instance",
        message=make_message(message_id=message_id),
        data=data,
    )
