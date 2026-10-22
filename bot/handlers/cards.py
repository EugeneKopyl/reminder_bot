from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot import texts
from bot.domain.parsing import ParseStatus, ReminderParser
from bot.domain.ports import Clock, ReminderService
from bot.handlers.common import parse_for_user, plain_text
from bot.telegram.callbacks import CardAction, CardCallback
from bot.telegram.formatting import describe_schedule
from bot.telegram.keyboards import card_keyboard, delete_confirmation_keyboard, status_keyboard
from bot.telegram.states import (
    ALTERNATIVES_KEY,
    TARGET_MESSAGE_KEY,
    TARGET_REMINDER_KEY,
    EditReminder,
    load_schedule,
)

router = Router(name="cards")


async def refresh_card(
    bot: Bot, reminder_service: ReminderService, user_id: int, reminder_id: str, message_id: int
) -> bool:
    summaries = await reminder_service.active_reminders(user_id)
    summary = next((item for item in summaries if item.reminder_id == reminder_id), None)
    if summary is None:
        return False
    await _set_markup(
        bot, user_id, message_id, card_keyboard(reminder_id, summary.schedule, summary.priority)
    )
    return True


async def _set_markup(
    bot: Bot, chat_id: int, message_id: int | None, markup: InlineKeyboardMarkup
) -> None:
    if message_id is None:
        return
    with suppress(TelegramBadRequest):
        await bot.edit_message_reply_markup(
            chat_id=chat_id, message_id=message_id, reply_markup=markup
        )


def _message_id(callback: CallbackQuery) -> int | None:
    return callback.message.message_id if callback.message is not None else None


@router.callback_query(CardCallback.filter(F.action == CardAction.EDIT))
async def start_edit(
    callback: CallbackQuery, callback_data: CardCallback, state: FSMContext, bot: Bot
) -> None:
    await state.set_state(EditReminder.waiting_schedule)
    await state.update_data(
        {TARGET_REMINDER_KEY: callback_data.reminder_id, TARGET_MESSAGE_KEY: _message_id(callback)}
    )
    await bot.send_message(chat_id=callback.from_user.id, text=texts.ASK_NEW_SCHEDULE)
    await bot.answer_callback_query(callback.id)


@router.message(EditReminder.waiting_schedule, plain_text)
async def apply_edit(
    message: Message,
    state: FSMContext,
    bot: Bot,
    reminder_service: ReminderService,
    parse_reminder: ReminderParser,
    clock: Clock,
) -> None:
    if message.from_user is None or message.text is None:
        return
    user_id = message.from_user.id
    now, _, result = await parse_for_user(
        reminder_service, parse_reminder, clock, user_id, message.text
    )
    if result.status is not ParseStatus.OK or result.draft is None:
        await bot.send_message(chat_id=user_id, text=texts.SCHEDULE_NOT_UNDERSTOOD)
        return
    data = await state.get_data()
    await state.set_state(None)
    reminder_id = data.get(TARGET_REMINDER_KEY, "")
    schedule = result.draft.schedule
    if not await reminder_service.replace_schedule(user_id, reminder_id, schedule):
        await bot.send_message(chat_id=user_id, text=texts.REMINDER_NOT_FOUND)
        return
    card_message_id = data.get(TARGET_MESSAGE_KEY)
    if card_message_id is not None:
        await refresh_card(bot, reminder_service, user_id, reminder_id, card_message_id)
    await bot.send_message(
        chat_id=user_id, text=texts.schedule_updated(describe_schedule(schedule, now.date()))
    )


@router.callback_query(CardCallback.filter(F.action == CardAction.ALTERNATIVE))
async def choose_alternative(
    callback: CallbackQuery,
    callback_data: CardCallback,
    state: FSMContext,
    bot: Bot,
    reminder_service: ReminderService,
) -> None:
    user_id = callback.from_user.id
    message_id = _message_id(callback)
    stored = (await state.get_data()).get(ALTERNATIVES_KEY) or {}
    schedules = stored.get("schedules", [])
    if stored.get("reminder_id") != callback_data.reminder_id or not (
        0 <= callback_data.index < len(schedules)
    ):
        if message_id is not None:
            await refresh_card(
                bot, reminder_service, user_id, callback_data.reminder_id, message_id
            )
        await bot.answer_callback_query(callback.id, text=texts.ALTERNATIVE_EXPIRED)
        return
    schedule = load_schedule(schedules[callback_data.index])
    await state.update_data({ALTERNATIVES_KEY: None})
    if not await reminder_service.replace_schedule(user_id, callback_data.reminder_id, schedule):
        await bot.answer_callback_query(callback.id, text=texts.REMINDER_NOT_FOUND)
        return
    if message_id is not None:
        await refresh_card(bot, reminder_service, user_id, callback_data.reminder_id, message_id)
    await bot.answer_callback_query(
        callback.id, text=texts.schedule_updated(describe_schedule(schedule))
    )


@router.callback_query(CardCallback.filter(F.action == CardAction.DELETE))
async def ask_delete_confirmation(
    callback: CallbackQuery, callback_data: CardCallback, bot: Bot
) -> None:
    await _set_markup(
        bot,
        callback.from_user.id,
        _message_id(callback),
        delete_confirmation_keyboard(callback_data.reminder_id),
    )
    await bot.answer_callback_query(callback.id)


@router.callback_query(CardCallback.filter(F.action == CardAction.DELETE_CONFIRM))
async def confirm_delete(
    callback: CallbackQuery,
    callback_data: CardCallback,
    bot: Bot,
    reminder_service: ReminderService,
) -> None:
    user_id = callback.from_user.id
    await reminder_service.delete_reminder(user_id, callback_data.reminder_id)
    await _set_markup(bot, user_id, _message_id(callback), status_keyboard(texts.DELETED))
    await bot.answer_callback_query(callback.id, text=texts.DELETED)


@router.callback_query(CardCallback.filter(F.action == CardAction.DELETE_CANCEL))
async def cancel_delete(
    callback: CallbackQuery,
    callback_data: CardCallback,
    bot: Bot,
    reminder_service: ReminderService,
) -> None:
    user_id = callback.from_user.id
    message_id = _message_id(callback)
    if message_id is not None and not await refresh_card(
        bot, reminder_service, user_id, callback_data.reminder_id, message_id
    ):
        await _set_markup(bot, user_id, message_id, status_keyboard(texts.DELETED))
    await bot.answer_callback_query(callback.id)


@router.callback_query(CardCallback.filter(F.action == CardAction.UNDO))
async def undo_reminder(
    callback: CallbackQuery,
    callback_data: CardCallback,
    bot: Bot,
    reminder_service: ReminderService,
) -> None:
    user_id = callback.from_user.id
    message_id = _message_id(callback)
    await reminder_service.delete_reminder(user_id, callback_data.reminder_id)
    if message_id is not None:
        try:
            await bot.delete_message(chat_id=user_id, message_id=message_id)
        except TelegramBadRequest:
            await _set_markup(bot, user_id, message_id, status_keyboard(texts.UNDONE))
    await bot.answer_callback_query(callback.id, text=texts.UNDONE)
