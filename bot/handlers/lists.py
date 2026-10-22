from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot import texts
from bot.domain.ports import Clock, ReminderService
from bot.telegram.callbacks import ListAction, ListCallback
from bot.telegram.formatting import render_all, render_period
from bot.telegram.keyboards import list_keyboard
from bot.telegram.periods import ListPeriod, period_window
from bot.telegram.timezones import local_now

router = Router(name="lists")

MAX_COPIED_CARDS = 100
COMMAND_PERIODS = {
    "today": ListPeriod.DAY,
    "week": ListPeriod.WEEK,
    "month": ListPeriod.MONTH,
    "all": ListPeriod.ALL,
}
MENU_PERIODS = {
    texts.MENU_TODAY: ListPeriod.DAY,
    texts.MENU_WEEK: ListPeriod.WEEK,
    texts.MENU_MONTH: ListPeriod.MONTH,
    texts.MENU_ALL: ListPeriod.ALL,
}


async def build_list(
    reminder_service: ReminderService, clock: Clock, user_id: int, period: ListPeriod, offset: int
) -> tuple[str, InlineKeyboardMarkup]:
    profile = await reminder_service.ensure_user(user_id)
    now = local_now(clock, profile.timezone)
    if period is ListPeriod.ALL:
        summaries = await reminder_service.active_reminders(user_id)
        has_cards = any(summary.card_message_id is not None for summary in summaries)
        return render_all(summaries, now.date()), list_keyboard(period, 0, has_cards)
    window = period_window(period, offset, now)
    fires = await reminder_service.planned_fires(user_id, window.start, window.end)
    has_cards = any(fire.card_message_id is not None for fire in fires)
    return render_period(window, fires, now.date()), list_keyboard(period, offset, has_cards)


async def collect_card_ids(
    reminder_service: ReminderService, clock: Clock, user_id: int, period: ListPeriod, offset: int
) -> list[int]:
    if period is ListPeriod.ALL:
        items = await reminder_service.active_reminders(user_id)
        card_ids = {summary.card_message_id for summary in items}
    else:
        profile = await reminder_service.ensure_user(user_id)
        window = period_window(period, offset, local_now(clock, profile.timezone))
        fires = await reminder_service.planned_fires(user_id, window.start, window.end)
        card_ids = {fire.card_message_id for fire in fires}
    return sorted(card_id for card_id in card_ids if card_id is not None)[:MAX_COPIED_CARDS]


async def send_list(
    bot: Bot, reminder_service: ReminderService, clock: Clock, user_id: int, period: ListPeriod
) -> None:
    text, keyboard = await build_list(reminder_service, clock, user_id, period, 0)
    await bot.send_message(chat_id=user_id, text=text, reply_markup=keyboard)


@router.message(Command(*COMMAND_PERIODS))
async def list_by_command(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    bot: Bot,
    reminder_service: ReminderService,
    clock: Clock,
) -> None:
    if message.from_user is None:
        return
    await state.set_state(None)
    period = COMMAND_PERIODS[command.command]
    await send_list(bot, reminder_service, clock, message.from_user.id, period)


@router.message(F.text.in_(MENU_PERIODS))
async def list_by_menu(
    message: Message,
    state: FSMContext,
    bot: Bot,
    reminder_service: ReminderService,
    clock: Clock,
) -> None:
    if message.from_user is None or message.text is None:
        return
    await state.set_state(None)
    period = MENU_PERIODS[message.text]
    await send_list(bot, reminder_service, clock, message.from_user.id, period)


@router.callback_query(ListCallback.filter(F.action == ListAction.SHOW))
async def navigate_list(
    callback: CallbackQuery,
    callback_data: ListCallback,
    bot: Bot,
    reminder_service: ReminderService,
    clock: Clock,
) -> None:
    user_id = callback.from_user.id
    text, keyboard = await build_list(
        reminder_service, clock, user_id, callback_data.period, callback_data.offset
    )
    if callback.message is not None:
        with suppress(TelegramBadRequest):
            await bot.edit_message_text(
                text=text,
                chat_id=user_id,
                message_id=callback.message.message_id,
                reply_markup=keyboard,
            )
    await bot.answer_callback_query(callback.id)


@router.callback_query(ListCallback.filter(F.action == ListAction.CARDS))
async def show_cards(
    callback: CallbackQuery,
    callback_data: ListCallback,
    bot: Bot,
    reminder_service: ReminderService,
    clock: Clock,
) -> None:
    user_id = callback.from_user.id
    card_ids = await collect_card_ids(
        reminder_service, clock, user_id, callback_data.period, callback_data.offset
    )
    if not card_ids:
        await bot.answer_callback_query(callback.id, text=texts.NO_CARDS)
        return
    await bot.copy_messages(chat_id=user_id, from_chat_id=user_id, message_ids=card_ids)
    await bot.answer_callback_query(callback.id)
