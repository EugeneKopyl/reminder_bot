from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from bot.domain.occurrences import (
    ActionOutcome,
    Notification,
    OccurrenceAction,
    PlannedFire,
    ReminderSummary,
)
from bot.domain.reminders import ReminderDraft, Schedule, UserProfile


class RecipientUnavailableError(Exception):
    pass


class Clock(Protocol):
    def now(self) -> datetime:
        """Timezone-aware current time in UTC."""
        ...


class Notifier(Protocol):
    async def notify(self, notification: Notification) -> int:
        """Delivers a notification and returns the sent message id.

        Raises RecipientUnavailableError when the user blocked the bot.
        """
        ...

    async def notify_missed(self, user_id: int, notifications: Sequence[Notification]) -> None: ...


class ReminderService(Protocol):
    """Datetimes passed in and returned are timezone-aware; returned ones are in the user's tz.

    Reminder text and tags are never persisted in plaintext.
    """

    async def ensure_user(self, user_id: int) -> UserProfile: ...

    async def set_timezone(self, user_id: int, timezone: str) -> UserProfile: ...

    async def create_reminder(self, user_id: int, draft: ReminderDraft) -> str: ...

    async def attach_card(self, user_id: int, reminder_id: str, message_id: int) -> None: ...

    async def replace_schedule(
        self, user_id: int, reminder_id: str, schedule: Schedule
    ) -> bool: ...

    async def delete_reminder(self, user_id: int, reminder_id: str) -> bool: ...

    async def apply_action(
        self, user_id: int, occurrence_id: int, action: OccurrenceAction
    ) -> ActionOutcome: ...

    async def planned_fires(
        self, user_id: int, start: datetime, end: datetime
    ) -> list[PlannedFire]: ...

    async def active_reminders(self, user_id: int) -> list[ReminderSummary]: ...
