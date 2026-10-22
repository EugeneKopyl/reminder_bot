import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Sequence

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from bot import texts
from bot.domain.occurrences import Notification
from bot.domain.ports import RecipientUnavailableError
from bot.telegram.formatting import format_time, render_missed
from bot.telegram.keyboards import notification_keyboard

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
STALE_CHAT_LIMIT = 10_000


class RateLimiter:
    def __init__(
        self,
        per_chat_interval: float = 1.0,
        global_interval: float = 1 / 30,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._per_chat_interval = per_chat_interval
        self._global_interval = global_interval
        self._monotonic = monotonic
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._global_ready_at = 0.0
        self._chat_ready_at: dict[int, float] = {}

    async def wait(self, chat_id: int) -> None:
        async with self._lock:
            now = self._monotonic()
            send_at = max(now, self._global_ready_at, self._chat_ready_at.get(chat_id, 0.0))
            self._global_ready_at = send_at + self._global_interval
            self._chat_ready_at[chat_id] = send_at + self._per_chat_interval
            if len(self._chat_ready_at) > STALE_CHAT_LIMIT:
                self._chat_ready_at = {
                    chat: ready_at
                    for chat, ready_at in self._chat_ready_at.items()
                    if ready_at > now
                }
        if send_at > now:
            await self._sleep(send_at - now)


class TelegramNotifier:
    def __init__(self, bot: Bot, rate_limiter: RateLimiter | None = None) -> None:
        self._bot = bot
        self._rate_limiter = rate_limiter or RateLimiter()

    async def notify(self, notification: Notification) -> int:
        chat_id = notification.user_id
        keyboard = notification_keyboard(notification)
        card_message_id = notification.card_message_id
        if card_message_id is not None:
            try:
                copied = await self._deliver(
                    chat_id,
                    lambda: self._bot.copy_message(
                        chat_id=chat_id,
                        from_chat_id=chat_id,
                        message_id=card_message_id,
                        reply_markup=keyboard,
                    ),
                )
                return copied.message_id
            except TelegramBadRequest:
                logger.info("card of reminder %s is unavailable", notification.reminder_id)
        sent = await self._deliver(
            chat_id,
            lambda: self._bot.send_message(
                chat_id=chat_id,
                text=texts.notification_fallback(format_time(notification.planned_at)),
                reply_markup=keyboard,
            ),
        )
        return sent.message_id

    async def notify_missed(self, user_id: int, notifications: Sequence[Notification]) -> None:
        if not notifications:
            return
        await self._deliver(
            user_id,
            lambda: self._bot.send_message(
                chat_id=user_id,
                text=render_missed(notifications),
                disable_notification=True,
            ),
        )

    async def _deliver[T](self, chat_id: int, request: Callable[[], Awaitable[T]]) -> T:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            await self._rate_limiter.wait(chat_id)
            try:
                return await request()
            except TelegramForbiddenError as error:
                raise RecipientUnavailableError(chat_id) from error
            except TelegramRetryAfter as error:
                if attempt == MAX_ATTEMPTS:
                    raise
                await asyncio.sleep(error.retry_after)
            except TelegramBadRequest as error:
                if "chat not found" in error.message.lower():
                    raise RecipientUnavailableError(chat_id) from error
                raise
        raise AssertionError("unreachable")
