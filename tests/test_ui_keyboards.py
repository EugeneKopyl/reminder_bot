from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardMarkup

from bot.domain.occurrences import Notification, OccurrenceKind
from bot.domain.reminders import Priority, Schedule, ScheduleKind
from bot.telegram.callbacks import CardAction, CardCallback, NotificationCallback
from bot.telegram.keyboards import (
    card_keyboard,
    delete_confirmation_keyboard,
    list_keyboard,
    notification_keyboard,
    timezone_keyboard,
)
from bot.telegram.periods import ListPeriod

UUID_LIKE_ID = "0192f3a4-7b5c-7d2e-9f10-1234567890ab"
MOSCOW = ZoneInfo("Europe/Moscow")
ONCE = Schedule(ScheduleKind.ONCE, datetime(2026, 10, 23, 9, 0))
DAILY = Schedule(ScheduleKind.RRULE, datetime(2026, 10, 23, 9, 0), rrule="FREQ=DAILY")


def make_notification(schedule: Schedule, overdue_by: timedelta = timedelta()) -> Notification:
    return Notification(
        occurrence_id=2**53,
        reminder_id=UUID_LIKE_ID,
        user_id=1,
        kind=OccurrenceKind.MAIN,
        card_message_id=7,
        schedule=schedule,
        priority=Priority.NORMAL,
        planned_at=datetime(2026, 10, 23, 9, 0, tzinfo=MOSCOW),
        overdue_by=overdue_by,
    )


def button_texts(markup: InlineKeyboardMarkup) -> list[list[str]]:
    return [[button.text for button in row] for row in markup.inline_keyboard]


def callback_payloads(markup: InlineKeyboardMarkup) -> list[str]:
    return [button.callback_data or "" for row in markup.inline_keyboard for button in row]


def test_every_callback_fits_telegram_limit() -> None:
    now = datetime(2026, 10, 22, tzinfo=MOSCOW)
    markups = [
        card_keyboard(UUID_LIKE_ID, DAILY, Priority.CRITICAL, ["07:00", "19:00", "21:00"]),
        delete_confirmation_keyboard(UUID_LIKE_ID),
        notification_keyboard(make_notification(DAILY)),
        list_keyboard(ListPeriod.MONTH, -1000, has_cards=True),
        timezone_keyboard(now),
    ]

    payloads = [payload for markup in markups for payload in callback_payloads(markup)]

    assert payloads
    assert all(0 < len(payload.encode()) <= 64 for payload in payloads)


def test_card_keyboard_offers_alternatives_and_actions() -> None:
    markup = card_keyboard(UUID_LIKE_ID, ONCE, Priority.NORMAL, ["19:00"])

    assert button_texts(markup) == [
        ["🕘 пт, 23 окт, 09:00 · однократно"],
        ["↔ 19:00"],
        ["✏️ Изменить", "🗑 Удалить", "↩️ Отменить"],
    ]
    alternative = CardCallback.unpack(callback_payloads(markup)[1])
    assert alternative == CardCallback(
        action=CardAction.ALTERNATIVE, reminder_id=UUID_LIKE_ID, index=0
    )


def test_notification_keyboard_for_one_time_reminder() -> None:
    assert button_texts(notification_keyboard(make_notification(ONCE))) == [
        ["🕘 09:00 · однократно"],
        ["✅ Готово", "⏰ 15 мин", "1 час"],
        ["🌅 Завтра утром", "🕐 Другое…"],
    ]


def test_notification_keyboard_for_overdue_recurring_reminder() -> None:
    markup = notification_keyboard(make_notification(DAILY, overdue_by=timedelta(hours=1)))

    rows = button_texts(markup)
    assert rows[0] == ["⚠️ Должно было прийти в 09:00"]
    assert rows[-1] == ["⏭ Пропустить", "⏹ Остановить серию"]
    snooze = NotificationCallback.unpack(callback_payloads(markup)[2])
    assert snooze.minutes == 15


def test_all_list_has_no_navigation() -> None:
    assert button_texts(list_keyboard(ListPeriod.ALL, 0, has_cards=True)) == [
        ["🗂 Показать карточки"]
    ]
    assert list_keyboard(ListPeriod.ALL, 0, has_cards=False).inline_keyboard == []
