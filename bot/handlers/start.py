from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.domain.ports import Clock, ReminderService
from bot.handlers.common import plain_text
from bot.telegram.callbacks import SettingsAction, SettingsCallback, TimezoneCallback
from bot.telegram.keyboards import main_menu_keyboard, settings_keyboard, timezone_keyboard
from bot.telegram.states import TimezoneInput
from bot.telegram.timezones import resolve_timezone, timezone_label

router = Router(name="start")


@router.message(CommandStart())
async def handle_start(
    message: Message,
    state: FSMContext,
    bot: Bot,
    reminder_service: ReminderService,
    clock: Clock,
) -> None:
    if message.from_user is None:
        return
    await state.clear()
    user_id = message.from_user.id
    profile = await reminder_service.ensure_user(user_id)
    await bot.send_message(chat_id=user_id, text=texts.START, reply_markup=main_menu_keyboard())
    if not profile.timezone_confirmed:
        now = clock.now()
        await bot.send_message(
            chat_id=user_id,
            text=texts.ask_timezone(timezone_label(profile.timezone, now)),
            reply_markup=timezone_keyboard(now),
        )


@router.message(Command("help"))
async def handle_help(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.set_state(None)
    await bot.send_message(chat_id=message.chat.id, text=texts.HELP)


@router.message(Command("cancel"))
async def handle_cancel(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.set_state(None)
    await bot.send_message(chat_id=message.chat.id, text=texts.CANCELLED)


@router.message(Command("settings"))
async def handle_settings(
    message: Message,
    state: FSMContext,
    bot: Bot,
    reminder_service: ReminderService,
    clock: Clock,
) -> None:
    if message.from_user is None:
        return
    await state.set_state(None)
    user_id = message.from_user.id
    profile = await reminder_service.ensure_user(user_id)
    await bot.send_message(
        chat_id=user_id,
        text=texts.settings(timezone_label(profile.timezone, clock.now())),
        reply_markup=settings_keyboard(),
    )


@router.callback_query(SettingsCallback.filter(F.action == SettingsAction.TIMEZONE))
async def show_timezone_picker(
    callback: CallbackQuery, bot: Bot, reminder_service: ReminderService, clock: Clock
) -> None:
    user_id = callback.from_user.id
    profile = await reminder_service.ensure_user(user_id)
    now = clock.now()
    await bot.send_message(
        chat_id=user_id,
        text=texts.ask_timezone(timezone_label(profile.timezone, now)),
        reply_markup=timezone_keyboard(now),
    )
    await bot.answer_callback_query(callback.id)


@router.callback_query(SettingsCallback.filter(F.action == SettingsAction.TIMEZONE_INPUT))
async def ask_timezone_name(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.set_state(TimezoneInput.waiting_name)
    await bot.send_message(chat_id=callback.from_user.id, text=texts.ASK_TIMEZONE_NAME)
    await bot.answer_callback_query(callback.id)


@router.callback_query(TimezoneCallback.filter())
async def choose_timezone(
    callback: CallbackQuery,
    callback_data: TimezoneCallback,
    bot: Bot,
    reminder_service: ReminderService,
    clock: Clock,
) -> None:
    user_id = callback.from_user.id
    zone = resolve_timezone(callback_data.zone)
    if zone is None:
        await bot.answer_callback_query(callback.id, text=texts.UNKNOWN_TIMEZONE)
        return
    await reminder_service.set_timezone(user_id, zone)
    text = texts.timezone_set(timezone_label(zone, clock.now()))
    if callback.message is not None:
        with suppress(TelegramBadRequest):
            await bot.edit_message_text(
                text=text, chat_id=user_id, message_id=callback.message.message_id
            )
    await bot.answer_callback_query(callback.id, text=text)


@router.message(TimezoneInput.waiting_name, plain_text)
async def receive_timezone_name(
    message: Message,
    state: FSMContext,
    bot: Bot,
    reminder_service: ReminderService,
    clock: Clock,
) -> None:
    if message.from_user is None or message.text is None:
        return
    await state.set_state(None)
    user_id = message.from_user.id
    zone = resolve_timezone(message.text)
    if zone is None:
        await bot.send_message(chat_id=user_id, text=texts.UNKNOWN_TIMEZONE)
        return
    await reminder_service.set_timezone(user_id, zone)
    await bot.send_message(
        chat_id=user_id, text=texts.timezone_set(timezone_label(zone, clock.now()))
    )
