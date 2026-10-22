import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from bot import texts
from bot.config import Settings
from bot.db.engine import create_engine, create_session_factory
from bot.db.schema import upgrade_database
from bot.handlers import build_router
from bot.middlewares.access import AccessMiddleware
from bot.nlu import parse_reminder
from bot.scheduling.clock import SystemClock
from bot.scheduling.scheduler import Scheduler
from bot.services.reminders import SqlReminderService
from bot.telegram.notifier import TelegramNotifier


async def run(settings: Settings) -> None:
    bot = Bot(
        settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    engine = create_engine(settings.database_path)
    sessions = create_session_factory(engine)
    clock = SystemClock()
    scheduler = Scheduler(sessions, TelegramNotifier(bot), clock)
    reminder_service = SqlReminderService(
        sessions, clock, settings.default_tz, on_schedule_change=scheduler.wake
    )

    dispatcher = Dispatcher(
        reminder_service=reminder_service,
        parse_reminder=parse_reminder,
        clock=clock,
    )
    dispatcher.update.outer_middleware(AccessMiddleware(settings.allowed_user_ids))
    dispatcher.include_router(build_router())

    scheduler_task: asyncio.Task[None] | None = None
    try:
        await bot.set_my_commands(
            [BotCommand(command=name, description=text) for name, text in texts.COMMANDS.items()]
        )
        scheduler_task = asyncio.create_task(scheduler.run())
        await dispatcher.start_polling(bot)
    finally:
        if scheduler_task is not None:
            scheduler_task.cancel()
            with suppress(asyncio.CancelledError):
                await scheduler_task
        await engine.dispose()
        await bot.session.close()


def main() -> None:
    settings = Settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    upgrade_database(settings.database_path)
    asyncio.run(run(settings))


if __name__ == "__main__":
    main()
