from unittest.mock import AsyncMock

from aiogram import Dispatcher
from aiogram.types import Update
from ui_fakes import (
    FakeReminderService,
    FixedClock,
    make_bot,
    make_callback,
    make_message,
    parser_returning,
)

from bot.domain.parsing import ParseResult, ParseStatus
from bot.handlers import build_router

DISPATCHER = Dispatcher()
DISPATCHER.include_router(build_router())


async def feed(update: Update, service: FakeReminderService, bot: AsyncMock) -> None:
    await DISPATCHER.feed_update(
        bot,
        update,
        reminder_service=service,
        parse_reminder=parser_returning(ParseResult(ParseStatus.NOT_UNDERSTOOD)),
        clock=FixedClock(),
    )


async def test_commands_reach_handlers_with_injected_dependencies() -> None:
    service = FakeReminderService()
    bot = make_bot()

    await feed(Update(update_id=1, message=make_message("/week")), service, bot)

    assert len(service.fire_windows) == 1
    assert bot.send_message.await_args.kwargs["text"].startswith("🗓 Неделя")


async def test_free_text_goes_to_parser() -> None:
    bot = make_bot()

    await feed(Update(update_id=2, message=make_message("ерунда")), FakeReminderService(), bot)

    assert bot.send_message.await_args.kwargs["text"].startswith("Не понял")


async def test_info_buttons_are_acknowledged() -> None:
    bot = make_bot()

    await feed(Update(update_id=3, callback_query=make_callback("_")), FakeReminderService(), bot)

    bot.answer_callback_query.assert_awaited_once()
