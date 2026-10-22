from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class AccessMiddleware(BaseMiddleware):
    def __init__(self, allowed_user_ids: frozenset[int]) -> None:
        self._allowed_user_ids = allowed_user_ids

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        if not self.is_allowed(data.get("event_from_user")):
            return None
        return await handler(event, data)

    def is_allowed(self, user: User | None) -> bool:
        if not self._allowed_user_ids:
            return True
        return user is not None and user.id in self._allowed_user_ids
