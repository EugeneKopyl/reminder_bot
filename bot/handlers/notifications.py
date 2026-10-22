from contextlib import suppress
from datetime import datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.domain.occurrences import (
    Done,
    OccurrenceAction,
    Skip,
    SnoozeFor,
    SnoozeUntil,
    StopSeries,
)
from bot.domain.parsing import ParseResult, ParseStatus, ReminderParser
from bot.domain.ports import Clock, ReminderService
from bot.domain.reminders import DayPeriodDefaults, ScheduleKind
from bot.handlers.common import parse_for_user, plain_text
from bot.telegram.callbacks import NotificationAction, NotificationCallback
from bot.telegram.formatting import action_result
from bot.telegram.keyboards import status_keyboard
from bot.telegram.states import TARGET_MESSAGE_KEY, TARGET_OCCURRENCE_KEY, SnoozeOccurrence
from bot.telegram.timezones import local_now

router = Router(name="notifications")


def to_occurrence_action(
    callback_data: NotificationCallback, now: datetime, day_periods: DayPeriodDefaults
) -> OccurrenceAction:
    match callback_data.action:
        case NotificationAction.DONE:
            return Done()
        case NotificationAction.SNOOZE:
            return SnoozeFor(timedelta(minutes=callback_data.minutes))
        case NotificationAction.TOMORROW:
            tomorrow = now.date() + timedelta(days=1)
            return SnoozeUntil(datetime.combine(tomorrow, day_periods.morning, tzinfo=now.tzinfo))
        case NotificationAction.SKIP:
            return Skip()
        case NotificationAction.STOP:
            return StopSeries()
    raise ValueError(f"{callback_data.action} needs user input")


def snooze_target(result: ParseResult, now: datetime) -> datetime | None:
    if result.status is not ParseStatus.OK or result.draft is None:
        return None
    schedule = result.draft.schedule
    if schedule.kind is not ScheduleKind.ONCE:
        return None
    target = schedule.start.replace(tzinfo=now.tzinfo)
    return target if target > now else None


async def _show_result(bot: Bot, chat_id: int, message_id: int | None, rows: list[str]) -> None:
    if message_id is None:
        return
    with suppress(TelegramBadRequest):
        await bot.edit_message_reply_markup(
            chat_id=chat_id, message_id=message_id, reply_markup=status_keyboard(*rows)
        )


@router.callback_query(NotificationCallback.filter(F.action == NotificationAction.OTHER))
async def ask_snooze_time(
    callback: CallbackQuery, callback_data: NotificationCallback, state: FSMContext, bot: Bot
) -> None:
    await state.set_state(SnoozeOccurrence.waiting_time)
    await state.update_data(
        {
            TARGET_OCCURRENCE_KEY: callback_data.occurrence_id,
            TARGET_MESSAGE_KEY: callback.message.message_id if callback.message else None,
        }
    )
    await bot.send_message(chat_id=callback.from_user.id, text=texts.ASK_SNOOZE_TIME)
    await bot.answer_callback_query(callback.id)


@router.callback_query(NotificationCallback.filter())
async def apply_notification_action(
    callback: CallbackQuery,
    callback_data: NotificationCallback,
    bot: Bot,
    reminder_service: ReminderService,
    clock: Clock,
) -> None:
    user_id = callback.from_user.id
    profile = await reminder_service.ensure_user(user_id)
    now = local_now(clock, profile.timezone)
    action = to_occurrence_action(callback_data, now, profile.day_periods)
    outcome = await reminder_service.apply_action(user_id, callback_data.occurrence_id, action)
    if not outcome.applied:
        await bot.answer_callback_query(callback.id, text=texts.ACTION_STALE)
        return
    message_id = callback.message.message_id if callback.message else None
    await _show_result(bot, user_id, message_id, action_result(action, outcome, now))
    await bot.answer_callback_query(callback.id)


@router.message(SnoozeOccurrence.waiting_time, plain_text)
async def apply_snooze_time(
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
    target = snooze_target(result, now)
    if target is None:
        await bot.send_message(chat_id=user_id, text=texts.SNOOZE_TIME_INVALID)
        return
    data = await state.get_data()
    await state.set_state(None)
    action = SnoozeUntil(target)
    outcome = await reminder_service.apply_action(user_id, data[TARGET_OCCURRENCE_KEY], action)
    if not outcome.applied:
        await bot.send_message(chat_id=user_id, text=texts.ACTION_STALE)
        return
    rows = action_result(action, outcome, now)
    await _show_result(bot, user_id, data.get(TARGET_MESSAGE_KEY), rows)
    await bot.send_message(chat_id=user_id, text=rows[0])
