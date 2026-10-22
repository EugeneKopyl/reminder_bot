from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import CopyMessage

from bot.domain.occurrences import Notification, OccurrenceKind
from bot.domain.ports import Notifier, RecipientUnavailableError
from bot.domain.reminders import Priority, Schedule, ScheduleKind
from bot.telegram.notifier import RateLimiter, TelegramNotifier

METHOD = CopyMessage(chat_id=1, from_chat_id=1, message_id=7)


def make_notification(card_message_id: int | None = 7) -> Notification:
    return Notification(
        occurrence_id=3,
        reminder_id="reminder",
        user_id=1,
        kind=OccurrenceKind.MAIN,
        card_message_id=card_message_id,
        schedule=Schedule(ScheduleKind.ONCE, datetime(2026, 10, 23, 9, 0)),
        priority=Priority.NORMAL,
        planned_at=datetime(2026, 10, 23, 9, 0, tzinfo=ZoneInfo("Europe/Moscow")),
        overdue_by=timedelta(),
    )


class InstantLimiter(RateLimiter):
    async def wait(self, chat_id: int) -> None:
        return None


def make_notifier(bot: AsyncMock) -> TelegramNotifier:
    return TelegramNotifier(bot, InstantLimiter())


async def test_notification_is_a_copy_of_the_card() -> None:
    bot = AsyncMock()
    bot.copy_message.return_value = SimpleNamespace(message_id=55)
    notifier: Notifier = make_notifier(bot)

    assert await notifier.notify(make_notification()) == 55
    assert bot.copy_message.await_args.kwargs["message_id"] == 7
    bot.send_message.assert_not_awaited()


async def test_missing_card_falls_back_to_plain_text() -> None:
    bot = AsyncMock()
    bot.copy_message.side_effect = TelegramBadRequest(METHOD, "message to copy not found")
    bot.send_message.return_value = SimpleNamespace(message_id=56)

    assert await make_notifier(bot).notify(make_notification()) == 56
    assert bot.send_message.await_args.kwargs["text"] == "🔔 Напоминание · 09:00"


async def test_blocked_user_is_reported_as_unavailable() -> None:
    bot = AsyncMock()
    bot.send_message.side_effect = TelegramForbiddenError(METHOD, "bot was blocked by the user")

    with pytest.raises(RecipientUnavailableError):
        await make_notifier(bot).notify(make_notification(card_message_id=None))


async def test_flood_control_is_retried() -> None:
    bot = AsyncMock()
    bot.copy_message.side_effect = [
        TelegramRetryAfter(METHOD, "flood", retry_after=0),
        SimpleNamespace(message_id=57),
    ]

    assert await make_notifier(bot).notify(make_notification()) == 57
    assert bot.copy_message.await_count == 2


async def test_rate_limiter_spaces_messages_per_chat_and_globally() -> None:
    sleeps: list[float] = []

    async def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    limiter = RateLimiter(
        per_chat_interval=1.0, global_interval=0.1, monotonic=lambda: 100.0, sleep=record_sleep
    )

    await limiter.wait(1)
    await limiter.wait(2)
    await limiter.wait(1)

    assert sleeps == pytest.approx([0.1, 1.0])
