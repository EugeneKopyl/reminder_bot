from collections.abc import Sequence
from contextlib import suppress
from dataclasses import replace
from datetime import datetime, time, timedelta

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReactionTypeEmoji, ReplyParameters

from bot import texts
from bot.domain.parsing import Alternative, ParseStatus, ReminderParser
from bot.domain.ports import Clock, ReminderService
from bot.domain.reminders import DayPeriodDefaults, ReminderDraft, Schedule, ScheduleKind
from bot.handlers.common import parse_for_user, plain_text
from bot.telegram.callbacks import QuickTime, QuickTimeCallback
from bot.telegram.keyboards import card_keyboard, quick_time_keyboard
from bot.telegram.states import (
    ALTERNATIVES_KEY,
    PENDING_MESSAGE_KEY,
    PENDING_TEXT_KEY,
    PendingReminder,
    dump_schedule,
)
from bot.telegram.timezones import local_now

router = Router(name="reminders")

CONFIRMATION_REACTION = "👌"


async def publish_reminder(
    bot: Bot,
    reminder_service: ReminderService,
    state: FSMContext,
    user_id: int,
    draft: ReminderDraft,
    reply_to_message_id: int | None,
    alternatives: Sequence[Alternative] = (),
) -> str:
    if not draft.text.strip():
        draft = replace(draft, text=texts.UNTITLED_REMINDER)
    reminder_id = await reminder_service.create_reminder(user_id, draft)
    card = await bot.send_message(
        chat_id=user_id,
        text=texts.card(draft.text),
        reply_markup=card_keyboard(
            reminder_id,
            draft.schedule,
            draft.priority,
            [alternative.label for alternative in alternatives],
        ),
        reply_parameters=(
            ReplyParameters(message_id=reply_to_message_id, allow_sending_without_reply=True)
            if reply_to_message_id is not None
            else None
        ),
    )
    await reminder_service.attach_card(user_id, reminder_id, card.message_id)
    await state.update_data(
        {
            ALTERNATIVES_KEY: {
                "reminder_id": reminder_id,
                "schedules": [
                    dump_schedule(alternative.draft.schedule) for alternative in alternatives
                ],
            }
            if alternatives
            else None
        }
    )
    if reply_to_message_id is not None:
        with suppress(TelegramBadRequest):
            await bot.set_message_reaction(
                chat_id=user_id,
                message_id=reply_to_message_id,
                reaction=[ReactionTypeEmoji(emoji=CONFIRMATION_REACTION)],
            )
    return reminder_id


def quick_time_schedule(
    option: QuickTime, now: datetime, day_periods: DayPeriodDefaults
) -> Schedule:
    wall_clock_now = now.replace(tzinfo=None, second=0, microsecond=0)
    if option is QuickTime.IN_HOUR:
        start = wall_clock_now + timedelta(hours=1)
    elif option is QuickTime.EVENING:
        start = _next_at(wall_clock_now, day_periods.evening)
    else:
        start = datetime.combine(wall_clock_now.date() + timedelta(days=1), day_periods.morning)
    return Schedule(kind=ScheduleKind.ONCE, start=start)


def _next_at(now: datetime, moment: time) -> datetime:
    candidate = datetime.combine(now.date(), moment)
    return candidate if candidate > now else candidate + timedelta(days=1)


async def ask_for_time(bot: Bot, state: FSMContext, message: Message, text: str) -> None:
    await state.set_state(PendingReminder.waiting_time)
    await state.update_data({PENDING_TEXT_KEY: text, PENDING_MESSAGE_KEY: message.message_id})
    await bot.send_message(
        chat_id=message.chat.id, text=texts.ASK_TIME, reply_markup=quick_time_keyboard()
    )


@router.message(PendingReminder.waiting_time, plain_text)
async def receive_pending_time(
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
    data = await state.get_data()
    _, _, result = await parse_for_user(
        reminder_service, parse_reminder, clock, user_id, message.text
    )
    if result.status is ParseStatus.OK and result.draft is not None:
        await state.set_state(None)
        if result.draft.text.strip():
            await publish_reminder(
                bot,
                reminder_service,
                state,
                user_id,
                result.draft,
                message.message_id,
                result.alternatives,
            )
            return
        draft = replace(result.draft, text=data.get(PENDING_TEXT_KEY, ""))
        await publish_reminder(
            bot, reminder_service, state, user_id, draft, data.get(PENDING_MESSAGE_KEY)
        )
        return
    if result.status is ParseStatus.NEEDS_TIME:
        await ask_for_time(bot, state, message, result.text)
        return
    await bot.send_message(chat_id=message.chat.id, text=texts.SCHEDULE_NOT_UNDERSTOOD)


@router.callback_query(QuickTimeCallback.filter())
async def choose_quick_time(
    callback: CallbackQuery,
    callback_data: QuickTimeCallback,
    state: FSMContext,
    bot: Bot,
    reminder_service: ReminderService,
    clock: Clock,
) -> None:
    user_id = callback.from_user.id
    data = await state.get_data()
    if (
        await state.get_state() != PendingReminder.waiting_time.state
        or PENDING_TEXT_KEY not in data
    ):
        await bot.answer_callback_query(callback.id, text=texts.PENDING_EXPIRED)
        return
    profile = await reminder_service.ensure_user(user_id)
    now = local_now(clock, profile.timezone)
    draft = ReminderDraft(
        text=data[PENDING_TEXT_KEY],
        schedule=quick_time_schedule(callback_data.option, now, profile.day_periods),
    )
    await state.set_state(None)
    await publish_reminder(
        bot, reminder_service, state, user_id, draft, data.get(PENDING_MESSAGE_KEY)
    )
    if callback.message is not None:
        with suppress(TelegramBadRequest):
            await bot.delete_message(chat_id=user_id, message_id=callback.message.message_id)
    await bot.answer_callback_query(callback.id)


@router.message(plain_text)
async def create_from_text(
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
    _, _, result = await parse_for_user(
        reminder_service, parse_reminder, clock, user_id, message.text
    )
    if result.status is ParseStatus.OK and result.draft is not None:
        await publish_reminder(
            bot,
            reminder_service,
            state,
            user_id,
            result.draft,
            message.message_id,
            result.alternatives,
        )
    elif result.status is ParseStatus.NEEDS_TIME:
        await ask_for_time(bot, state, message, result.text)
    else:
        await bot.send_message(chat_id=message.chat.id, text=texts.NOT_UNDERSTOOD)
