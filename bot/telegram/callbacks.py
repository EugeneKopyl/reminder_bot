from enum import StrEnum

from aiogram.filters.callback_data import CallbackData

from bot.telegram.periods import ListPeriod


class CardAction(StrEnum):
    EDIT = "e"
    DELETE = "d"
    DELETE_CONFIRM = "dy"
    DELETE_CANCEL = "dn"
    UNDO = "u"
    ALTERNATIVE = "a"


class CardCallback(CallbackData, prefix="c"):
    action: CardAction
    reminder_id: str
    index: int = 0


class NotificationAction(StrEnum):
    DONE = "d"
    SNOOZE = "s"
    TOMORROW = "t"
    OTHER = "o"
    SKIP = "k"
    STOP = "x"


class NotificationCallback(CallbackData, prefix="n"):
    action: NotificationAction
    occurrence_id: int
    minutes: int = 0


class QuickTime(StrEnum):
    IN_HOUR = "h"
    EVENING = "e"
    TOMORROW_MORNING = "m"


class QuickTimeCallback(CallbackData, prefix="q"):
    option: QuickTime


class ListAction(StrEnum):
    SHOW = "s"
    CARDS = "c"


class ListCallback(CallbackData, prefix="l"):
    period: ListPeriod
    offset: int = 0
    action: ListAction = ListAction.SHOW


class SettingsAction(StrEnum):
    TIMEZONE = "tz"
    TIMEZONE_INPUT = "tzi"


class SettingsCallback(CallbackData, prefix="s"):
    action: SettingsAction


class TimezoneCallback(CallbackData, prefix="z"):
    zone: str


class NoopCallback(CallbackData, prefix="_"):
    pass
