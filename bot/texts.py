from html import escape

START = (
    "Привет! Я напомню о чём угодно.\n\n"
    "Напишите или надиктуйте одной фразой, что и когда напомнить, например:\n"
    "<i>завтра в 9 позвонить маме</i>\n"
    "<i>по будням в 8 и в 20 таблетки</i>"
)

HELP = (
    "Напишите одной фразой, что и когда напомнить:\n"
    "<i>через 20 минут выключить духовку</i>\n"
    "<i>завтра в 9 позвонить маме</i>\n"
    "<i>в пятницу вечером купить подарок</i>\n"
    "<i>каждый день в 8 и в 20 таблетки</i>\n"
    "<i>по будням в 9:00 планёрка</i>\n"
    "<i>каждый второй вторник месяца в 10 отчёт</i>\n\n"
    "Списки: /today, /week, /month, /all\n"
    "Настройки: /settings\n"
    "Отменить текущее действие: /cancel"
)

NOT_UNDERSTOOD = (
    "Не понял, что и когда напомнить. Например: «завтра в 9 позвонить маме». Подробнее — /help."
)
ONLY_TEXT = "Пока я понимаю только текст. Голосовые сообщения скоро появятся."
CANCELLED = "Отменено."

MENU_TODAY = "📅 Сегодня"
MENU_WEEK = "🗓 Неделя"
MENU_MONTH = "📆 Месяц"
MENU_ALL = "📋 Все"

SETTINGS_TIMEZONE_BUTTON = "🌍 Часовой пояс"
OTHER_TIMEZONE_BUTTON = "✍️ Другой пояс"
ASK_TIMEZONE_NAME = (
    "Напишите часовой пояс в формате <code>Europe/Berlin</code> или город из списка."
)
UNKNOWN_TIMEZONE = "Не нашёл такой часовой пояс. Выберите его в /settings."


def ask_timezone(current: str) -> str:
    return f"В каком вы часовом поясе? Сейчас выбран: {current}."


def timezone_set(label: str) -> str:
    return f"🌍 Часовой пояс: {label}"


def settings(timezone_label: str) -> str:
    return f"⚙️ Настройки\n\n🌍 Часовой пояс: {timezone_label}"


UNTITLED_REMINDER = "Напоминание"
CARD_EDIT = "✏️ Изменить"
CARD_DELETE = "🗑 Удалить"
CARD_UNDO = "↩️ Отменить"
DELETE_CONFIRM = "🗑 Да, удалить"
DELETE_CANCEL = "Отмена"
DELETED = "🗑 Удалено"
UNDONE = "↩️ Отменено"
REMINDER_NOT_FOUND = "Это напоминание уже удалено."
ALTERNATIVE_EXPIRED = "Этот вариант уже неактуален."
ASK_NEW_SCHEDULE = (
    "Напишите новое время или расписание, например «завтра в 18:00» или «по будням в 9». "
    "Отмена — /cancel."
)
SCHEDULE_NOT_UNDERSTOOD = (
    "Не понял время. Попробуйте ещё раз, например «в пятницу в 10». Отмена — /cancel."
)


def card(text: str) -> str:
    return f"🔔 {escape(text)}"


def alternative_button(label: str) -> str:
    return f"↔ {label}"


def schedule_updated(description: str) -> str:
    return f"Готово: {description}"


ASK_TIME = (
    "Когда напомнить? Выберите вариант или напишите время, "
    "например «в 18:30» или «в пятницу утром»."
)
QUICK_IN_HOUR = "Через час"
QUICK_EVENING = "Сегодня вечером"
QUICK_TOMORROW_MORNING = "Завтра утром"
PENDING_EXPIRED = "Не нашёл текст напоминания — напишите его ещё раз."

NOTIFY_DONE = "✅ Готово"
NOTIFY_SNOOZE_15 = "⏰ 15 мин"
NOTIFY_SNOOZE_60 = "1 час"
NOTIFY_TOMORROW = "🌅 Завтра утром"
NOTIFY_OTHER = "🕐 Другое…"
NOTIFY_SKIP = "⏭ Пропустить"
NOTIFY_STOP = "⏹ Остановить серию"
SKIPPED = "⏭ Пропущено"
SERIES_STOPPED = "⏹ Серия остановлена"
ACTION_STALE = "Это напоминание уже обработано."
ASK_SNOOZE_TIME = (
    "На когда отложить? Например «через 40 минут», «в 18:30» или «в понедельник». Отмена — /cancel."
)
SNOOZE_TIME_INVALID = "Нужно одно время в будущем, например «через 40 минут». Отмена — /cancel."


def notification_fallback(time_label: str) -> str:
    return f"🔔 Напоминание · {time_label}"


def overdue(when: str) -> str:
    return f"⚠️ Должно было прийти {when}"


def upcoming(time_label: str) -> str:
    return f"⏳ Скоро · в {time_label}"


def repeated(time_label: str) -> str:
    return f"🔔 Повтор · {time_label}"


def done_at(time_label: str) -> str:
    return f"✅ Выполнено в {time_label}"


def snoozed_until(when: str) -> str:
    return f"⏰ Отложено до {when}"


def next_fire(when: str) -> str:
    return f"Далее: {when}"


def missed(count_phrase: str) -> str:
    return f"⚠️ Пока бот был недоступен, пропущено: {count_phrase}"


TODAY = "Сегодня"
TOMORROW = "Завтра"
YESTERDAY = "Вчера"
NOTHING_PLANNED = "Ничего не запланировано."
NO_REMINDERS = "Напоминаний пока нет."
SHOW_CARDS = "🗂 Показать карточки"
NO_CARDS = "Карточек для показа нет."
PREVIOUS_PAGE = "◀"
NEXT_PAGE = "▶"
LIST_TRUNCATED = "…"


def day_title(label: str) -> str:
    return f"📅 {label}"


def week_title(date_range: str) -> str:
    return f"🗓 Неделя · {date_range}"


def month_title(month_label: str) -> str:
    return f"📆 {month_label}"


def all_title(count_phrase: str) -> str:
    return f"📋 Все напоминания — {count_phrase}"
