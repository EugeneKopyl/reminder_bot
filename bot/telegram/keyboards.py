from collections.abc import Sequence
from datetime import date, datetime

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from bot import texts
from bot.domain.occurrences import Notification
from bot.domain.reminders import Priority, Schedule
from bot.telegram.callbacks import (
    CardAction,
    CardCallback,
    ListAction,
    ListCallback,
    NoopCallback,
    NotificationAction,
    NotificationCallback,
    QuickTime,
    QuickTimeCallback,
    SettingsAction,
    SettingsCallback,
    TimezoneCallback,
)
from bot.telegram.formatting import card_info, is_recurring, notification_info
from bot.telegram.periods import ListPeriod
from bot.telegram.timezones import CITY_TIMEZONES, utc_offset_label

SNOOZE_SHORT_MINUTES = 15
SNOOZE_LONG_MINUTES = 60
TIMEZONE_COLUMNS = 2
MAX_ALTERNATIVES = 3

Row = list[InlineKeyboardButton]


def info_button(text: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=NoopCallback().pack())


def status_keyboard(*rows: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[info_button(row)] for row in rows])


def card_keyboard(
    reminder_id: str,
    schedule: Schedule,
    priority: Priority,
    alternative_labels: Sequence[str] = (),
    reference: date | None = None,
) -> InlineKeyboardMarkup:
    def card_button(text: str, action: CardAction, index: int = 0) -> InlineKeyboardButton:
        callback = CardCallback(action=action, reminder_id=reminder_id, index=index)
        return InlineKeyboardButton(text=text, callback_data=callback.pack())

    rows: list[Row] = [[info_button(card_info(schedule, priority, reference))]]
    if alternative_labels:
        rows.append(
            [
                card_button(texts.alternative_button(label), CardAction.ALTERNATIVE, index)
                for index, label in enumerate(alternative_labels[:MAX_ALTERNATIVES])
            ]
        )
    rows.append(
        [
            card_button(texts.CARD_EDIT, CardAction.EDIT),
            card_button(texts.CARD_DELETE, CardAction.DELETE),
            card_button(texts.CARD_UNDO, CardAction.UNDO),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def delete_confirmation_keyboard(reminder_id: str) -> InlineKeyboardMarkup:
    confirm = CardCallback(action=CardAction.DELETE_CONFIRM, reminder_id=reminder_id)
    cancel = CardCallback(action=CardAction.DELETE_CANCEL, reminder_id=reminder_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=texts.DELETE_CONFIRM, callback_data=confirm.pack()),
                InlineKeyboardButton(text=texts.DELETE_CANCEL, callback_data=cancel.pack()),
            ]
        ]
    )


def notification_keyboard(notification: Notification) -> InlineKeyboardMarkup:
    def action_button(
        text: str, action: NotificationAction, minutes: int = 0
    ) -> InlineKeyboardButton:
        callback = NotificationCallback(
            action=action, occurrence_id=notification.occurrence_id, minutes=minutes
        )
        return InlineKeyboardButton(text=text, callback_data=callback.pack())

    rows: list[Row] = [
        [info_button(notification_info(notification))],
        [
            action_button(texts.NOTIFY_DONE, NotificationAction.DONE),
            action_button(texts.NOTIFY_SNOOZE_15, NotificationAction.SNOOZE, SNOOZE_SHORT_MINUTES),
            action_button(texts.NOTIFY_SNOOZE_60, NotificationAction.SNOOZE, SNOOZE_LONG_MINUTES),
        ],
        [
            action_button(texts.NOTIFY_TOMORROW, NotificationAction.TOMORROW),
            action_button(texts.NOTIFY_OTHER, NotificationAction.OTHER),
        ],
    ]
    if is_recurring(notification.schedule):
        rows.append(
            [
                action_button(texts.NOTIFY_SKIP, NotificationAction.SKIP),
                action_button(texts.NOTIFY_STOP, NotificationAction.STOP),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def quick_time_keyboard() -> InlineKeyboardMarkup:
    options = (
        (texts.QUICK_IN_HOUR, QuickTime.IN_HOUR),
        (texts.QUICK_EVENING, QuickTime.EVENING),
        (texts.QUICK_TOMORROW_MORNING, QuickTime.TOMORROW_MORNING),
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=text, callback_data=QuickTimeCallback(option=option).pack()
                )
                for text, option in options
            ]
        ]
    )


def list_keyboard(period: ListPeriod, offset: int, has_cards: bool) -> InlineKeyboardMarkup:
    def list_button(text: str, target_offset: int, action: ListAction) -> InlineKeyboardButton:
        callback = ListCallback(period=period, offset=target_offset, action=action)
        return InlineKeyboardButton(text=text, callback_data=callback.pack())

    row: Row = []
    if period is not ListPeriod.ALL:
        row.append(list_button(texts.PREVIOUS_PAGE, offset - 1, ListAction.SHOW))
    if has_cards:
        row.append(list_button(texts.SHOW_CARDS, offset, ListAction.CARDS))
    if period is not ListPeriod.ALL:
        row.append(list_button(texts.NEXT_PAGE, offset + 1, ListAction.SHOW))
    return InlineKeyboardMarkup(inline_keyboard=[row] if row else [])


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.MENU_TODAY), KeyboardButton(text=texts.MENU_WEEK)],
            [KeyboardButton(text=texts.MENU_MONTH), KeyboardButton(text=texts.MENU_ALL)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def settings_keyboard() -> InlineKeyboardMarkup:
    callback = SettingsCallback(action=SettingsAction.TIMEZONE)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.SETTINGS_TIMEZONE_BUTTON, callback_data=callback.pack()
                )
            ]
        ]
    )


def timezone_keyboard(moment: datetime) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=f"{city} ({utc_offset_label(zone, moment)})",
            callback_data=TimezoneCallback(zone=zone).pack(),
        )
        for city, zone in CITY_TIMEZONES
    ]
    rows: list[Row] = [
        buttons[index : index + TIMEZONE_COLUMNS]
        for index in range(0, len(buttons), TIMEZONE_COLUMNS)
    ]
    other = SettingsCallback(action=SettingsAction.TIMEZONE_INPUT)
    rows.append(
        [InlineKeyboardButton(text=texts.OTHER_TIMEZONE_BUTTON, callback_data=other.pack())]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
