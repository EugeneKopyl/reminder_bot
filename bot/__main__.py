import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import Settings
from bot.handlers import build_router
from bot.middlewares.access import AccessMiddleware


async def main() -> None:
    settings = Settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    bot = Bot(
        settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.update.outer_middleware(AccessMiddleware(settings.allowed_user_ids))
    dispatcher.include_router(build_router())

    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
