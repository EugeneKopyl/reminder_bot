from collections.abc import Iterable, Sequence
from datetime import date, datetime, time, timedelta
from itertools import groupby, pairwise
from typing import assert_never

from bot import texts
from bot.domain.occurrences import (
    ActionOutcome,
    Done,
    Notification,
    OccurrenceAction,
    OccurrenceKind,
    PlannedFire,
    ReminderSummary,
    Skip,
    SnoozeFor,
    SnoozeUntil,
    StopSeries,
)
from bot.domain.reminders import Priority, Schedule, ScheduleKind
from bot.telegram.periods import ListPeriod, PeriodWindow

WEEKDAYS_SHORT = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
MONTHS_SHORT = ("янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек")
MONTHS_GENITIVE = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)  # fmt: skip
MONTHS_NOMINATIVE = (
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
)  # fmt: skip

WEEKDAY_CODES = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
WEEKDAYS_DATIVE_PLURAL = (
    "понедельникам", "вторникам", "средам", "четвергам", "пятницам", "субботам", "воскресеньям",
)  # fmt: skip
WEEKDAYS_ACCUSATIVE = (
    "понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье",
)  # fmt: skip
MASCULINE, FEMININE, NEUTER = "m", "f", "n"
WEEKDAY_GENDERS = (MASCULINE, MASCULINE, FEMININE, MASCULINE, FEMININE, FEMININE, NEUTER)

DAYS = ("день", "дня", "дней")
DAYS_ACCUSATIVE = DAYS
WEEKS_ACCUSATIVE = ("неделю", "недели", "недель")
MONTHS = ("месяц", "месяца", "месяцев")
HOURS = ("час", "часа", "часов")
MINUTES_ACCUSATIVE = ("минуту", "минуты", "минут")
TIMES = ("раз", "раза", "раз")
REMINDERS = ("напоминание", "напоминания", "напоминаний")

PRIORITY_MARKS = {Priority.NORMAL: "", Priority.IMPORTANT: "❗", Priority.CRITICAL: "‼️"}
RECURRING_MARK = "🔁"
ONCE_MARK = "🕘"
OVERDUE_NOTICE_AFTER = timedelta(minutes=15)
LIST_TEXT_LIMIT = 3800


def plural(count: int, forms: tuple[str, str, str]) -> str:
    count = abs(count)
    if count % 10 == 1 and count % 100 != 11:
        return forms[0]
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return forms[1]
    return forms[2]


def count_phrase(count: int, forms: tuple[str, str, str]) -> str:
    return f"{count} {plural(count, forms)}"


def join_words(items: Sequence[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} и {items[-1]}"


def format_time(moment: datetime | time) -> str:
    return f"{moment.hour:02d}:{moment.minute:02d}"


def format_day(day: date, reference: date | None = None) -> str:
    label = f"{WEEKDAYS_SHORT[day.weekday()]}, {day.day} {MONTHS_SHORT[day.month - 1]}"
    if reference is not None and day.year != reference.year:
        label += f" {day.year}"
    return label


def format_moment(moment: datetime, reference: date | None = None) -> str:
    return f"{format_day(moment.date(), reference)}, {format_time(moment)}"


def format_relative_moment(moment: datetime, now: datetime) -> str:
    if moment.date() == now.date():
        return format_time(moment)
    return format_moment(moment, now.date())


def priority_mark(priority: Priority) -> str:
    return PRIORITY_MARKS[priority]


def with_priority(text: str, priority: Priority) -> str:
    mark = priority_mark(priority)
    return f"{mark} {text}" if mark else text


def is_recurring(schedule: Schedule) -> bool:
    return schedule.kind is not ScheduleKind.ONCE


def describe_duration(duration: timedelta) -> str:
    minutes = int(duration.total_seconds() // 60)
    if minutes % (7 * 24 * 60) == 0:
        amount, forms = minutes // (7 * 24 * 60), WEEKS_ACCUSATIVE
    elif minutes % (24 * 60) == 0:
        amount, forms = minutes // (24 * 60), DAYS_ACCUSATIVE
    elif minutes % 60 == 0:
        amount, forms = minutes // 60, HOURS
    else:
        amount, forms = minutes, MINUTES_ACCUSATIVE
    return forms[0] if amount == 1 else count_phrase(amount, forms)


def describe_schedule(schedule: Schedule, reference: date | None = None) -> str:
    if schedule.kind is ScheduleKind.ONCE:
        return f"{format_moment(schedule.start, reference)} · однократно"
    if schedule.kind is ScheduleKind.AFTER_COMPLETION and schedule.interval_after_done:
        return f"через {describe_duration(schedule.interval_after_done)} после выполнения"
    if schedule.rrule:
        return describe_rrule(schedule.rrule, schedule.start, reference)
    return "по особому расписанию"


def describe_rrule(rule: str, start: datetime, reference: date | None = None) -> str:
    parts = _rule_parts(rule)
    interval = _first_int(parts.get("INTERVAL")) or 1
    frequency = parts.get("FREQ", "")
    times = _rule_times(parts, start)

    if frequency == "MINUTELY":
        body = (
            "каждую минуту"
            if interval == 1
            else f"каждые {count_phrase(interval, MINUTES_ACCUSATIVE)}"
        )
    elif frequency == "HOURLY":
        body = "каждый час" if interval == 1 else f"каждые {count_phrase(interval, HOURS)}"
    elif frequency == "DAILY":
        times_phrase = _times_phrase(times)
        if interval == 1 and not times_phrase.startswith("в "):
            body = times_phrase
        else:
            body = f"{_every(interval, DAYS, 'каждый день')} {times_phrase}"
    elif frequency == "WEEKLY":
        body = f"{_weekly_phrase(parts, start, interval)} {_times_phrase(times)}"
    elif frequency == "MONTHLY":
        body = f"{_monthly_phrase(parts, start, interval)} {_times_phrase(times)}"
    elif frequency == "YEARLY":
        body = f"{_yearly_phrase(parts, start)} {_times_phrase(times)}"
    else:
        return "по особому расписанию"
    return body + _limit_suffix(parts, reference)


def card_info(schedule: Schedule, priority: Priority, reference: date | None = None) -> str:
    mark = RECURRING_MARK if is_recurring(schedule) else ONCE_MARK
    return with_priority(f"{mark} {describe_schedule(schedule, reference)}", priority)


def notification_info(notification: Notification) -> str:
    planned_at = notification.planned_at
    if notification.overdue_by > OVERDUE_NOTICE_AFTER:
        when = (
            f"в {format_time(planned_at)}"
            if notification.overdue_by < timedelta(hours=12)
            else format_moment(planned_at)
        )
        info = texts.overdue(when)
    elif notification.kind is OccurrenceKind.PRE:
        info = texts.upcoming(format_time(planned_at))
    elif notification.kind is OccurrenceKind.NAG:
        info = texts.repeated(format_time(planned_at))
    elif is_recurring(notification.schedule):
        info = f"{RECURRING_MARK} {describe_schedule(notification.schedule)}"
    else:
        info = f"{ONCE_MARK} {format_time(planned_at)} · однократно"
    return with_priority(info, notification.priority)


def action_result(action: OccurrenceAction, outcome: ActionOutcome, now: datetime) -> list[str]:
    match action:
        case Done():
            rows = [texts.done_at(format_time(now))]
        case SnoozeFor(delta=delta):
            target = outcome.next_fire_at or now + delta
            return [texts.snoozed_until(format_relative_moment(target, now))]
        case SnoozeUntil(local_time=local_time):
            target = outcome.next_fire_at or local_time
            return [texts.snoozed_until(format_relative_moment(target, now))]
        case Skip():
            rows = [texts.SKIPPED]
        case StopSeries():
            return [texts.SERIES_STOPPED]
        case _:
            assert_never(action)
    if outcome.next_fire_at is not None and not outcome.series_finished:
        rows.append(texts.next_fire(format_relative_moment(outcome.next_fire_at, now)))
    return rows


def render_period(window: PeriodWindow, fires: Sequence[PlannedFire], today: date) -> str:
    title = _period_title(window, today)
    if not fires:
        return f"{title}\n\n{texts.NOTHING_PLANNED}"
    header = f"{title} — {count_phrase(len(fires), REMINDERS)}"
    ordered = sorted(fires, key=lambda fire: fire.at)
    if window.period is ListPeriod.DAY:
        lines = [_fire_line(fire) for fire in ordered]
    else:
        lines = []
        for day, day_fires in groupby(ordered, key=lambda fire: fire.at.date()):
            lines.append(f"\n<b>{format_day(day, today)}</b>")
            lines.extend(_fire_line(fire) for fire in day_fires)
    return _limited(header, lines)


def render_all(summaries: Sequence[ReminderSummary], today: date) -> str:
    if not summaries:
        return f"{texts.all_title('0')}\n\n{texts.NO_REMINDERS}"
    header = texts.all_title(str(len(summaries)))
    ordered = sorted(
        summaries,
        key=lambda summary: (
            summary.next_fire_at is None,
            summary.next_fire_at or summary.schedule.start,
        ),
    )
    return _limited(header, [_summary_line(summary, today) for summary in ordered])


def render_missed(notifications: Sequence[Notification]) -> str:
    header = texts.missed(count_phrase(len(notifications), REMINDERS))
    ordered = sorted(notifications, key=lambda notification: notification.planned_at)
    lines = [
        _marked(
            format_moment(notification.planned_at), notification.schedule, notification.priority
        )
        for notification in ordered
    ]
    return _limited(header, lines)


def _period_title(window: PeriodWindow, today: date) -> str:
    start = window.start.date()
    if window.period is ListPeriod.DAY:
        relative = {0: texts.TODAY, 1: texts.TOMORROW, -1: texts.YESTERDAY}.get(
            (start - today).days
        )
        day = format_day(start, today)
        return texts.day_title(f"{relative} · {day}" if relative else day)
    if window.period is ListPeriod.WEEK:
        return texts.week_title(_week_range(start, start + timedelta(days=6)))
    return texts.month_title(f"{MONTHS_NOMINATIVE[start.month - 1]} {start.year}")


def _week_range(first: date, last: date) -> str:
    if first.month == last.month:
        return f"{first.day}–{last.day} {MONTHS_SHORT[last.month - 1]}"
    return (
        f"{first.day} {MONTHS_SHORT[first.month - 1]} – {last.day} {MONTHS_SHORT[last.month - 1]}"
    )


def _fire_line(fire: PlannedFire) -> str:
    return _marked(format_time(fire.at), fire.schedule, fire.priority)


def _summary_line(summary: ReminderSummary, today: date) -> str:
    if summary.next_fire_at is None:
        return with_priority(
            f"{RECURRING_MARK} {describe_schedule(summary.schedule, today)}", summary.priority
        )
    moment = format_moment(summary.next_fire_at, today)
    if is_recurring(summary.schedule):
        moment += f" — {RECURRING_MARK} {describe_schedule(summary.schedule, today)}"
    mark = priority_mark(summary.priority)
    return f"{moment} {mark}" if mark else moment


def _marked(label: str, schedule: Schedule, priority: Priority) -> str:
    marks = [
        mark
        for mark in (RECURRING_MARK if is_recurring(schedule) else "", priority_mark(priority))
        if mark
    ]
    return " ".join([label, *marks])


def _limited(header: str, lines: Iterable[str]) -> str:
    text = header + "\n"
    for line in lines:
        if len(text) + len(line) + 1 > LIST_TEXT_LIMIT:
            return f"{text}\n{texts.LIST_TRUNCATED}"
        text += f"\n{line}"
    return text


def _rule_parts(rule: str) -> dict[str, str]:
    rule = rule.removeprefix("RRULE:")
    parts: dict[str, str] = {}
    for chunk in rule.split(";"):
        key, separator, value = chunk.partition("=")
        if separator:
            parts[key.strip().upper()] = value.strip().upper()
    return parts


def _ints(raw: str | None) -> list[int]:
    if not raw:
        return []
    try:
        return [int(value) for value in raw.split(",") if value]
    except ValueError:
        return []


def _first_int(raw: str | None) -> int | None:
    values = _ints(raw)
    return values[0] if values else None


def _rule_times(parts: dict[str, str], start: datetime) -> list[time]:
    hours = [hour for hour in _ints(parts.get("BYHOUR")) if 0 <= hour <= 23] or [start.hour]
    minutes = [minute for minute in _ints(parts.get("BYMINUTE")) if 0 <= minute <= 59] or [
        start.minute
    ]
    return sorted(time(hour, minute) for hour in hours for minute in minutes)


def _times_phrase(times: Sequence[time]) -> str:
    if len(times) >= 4 and len({moment.minute for moment in times}) == 1:
        steps = {later.hour - earlier.hour for earlier, later in pairwise(times)}
        if len(steps) == 1:
            step = steps.pop()
            every = "каждый час" if step == 1 else f"каждые {count_phrase(step, HOURS)}"
            return f"{every} с {format_time(times[0])} до {format_time(times[-1])}"
    return "в " + join_words([format_time(moment) for moment in times])


def _every(interval: int, forms: tuple[str, str, str], single: str) -> str:
    if interval == 1:
        return single
    word = "каждый" if plural(interval, forms) == forms[0] else "каждые"
    return f"{word} {count_phrase(interval, forms)}"


def _weekday_indexes(parts: dict[str, str]) -> list[int]:
    indexes = []
    for code in parts.get("BYDAY", "").split(","):
        weekday = code.lstrip("+-0123456789")
        if weekday in WEEKDAY_CODES:
            indexes.append(WEEKDAY_CODES.index(weekday))
    return sorted(set(indexes))


def _weekly_phrase(parts: dict[str, str], start: datetime, interval: int) -> str:
    days = _weekday_indexes(parts) or [start.weekday()]
    if days == [0, 1, 2, 3, 4]:
        phrase = "по будням"
    elif days == [5, 6]:
        phrase = "по выходным"
    elif len(days) == 7:
        phrase = "каждый день"
    else:
        phrase = "по " + join_words([WEEKDAYS_DATIVE_PLURAL[day] for day in days])
    if interval > 1:
        phrase = f"раз в {count_phrase(interval, WEEKS_ACCUSATIVE)}, {phrase}"
    return phrase


def _monthly_phrase(parts: dict[str, str], start: datetime, interval: int) -> str:
    phrase = _monthly_days(parts) or _monthly_weekday(parts) or f"каждое {start.day}-е число"
    if interval > 1:
        phrase = f"раз в {count_phrase(interval, MONTHS)}, {phrase}"
    return phrase


def _monthly_days(parts: dict[str, str]) -> str | None:
    days = _ints(parts.get("BYMONTHDAY"))
    if days == [-1]:
        return "в последний день месяца"
    positive_days = [day for day in days if day > 0]
    if not positive_days:
        return None
    return "каждое " + join_words([f"{day}-е" for day in positive_days]) + " число"


def _monthly_weekday(parts: dict[str, str]) -> str | None:
    code = parts.get("BYDAY", "").split(",")[0]
    ordinal_text, weekday = code[:-2], code[-2:]
    if weekday not in WEEKDAY_CODES or not ordinal_text:
        return None
    try:
        ordinal = int(ordinal_text)
    except ValueError:
        return None
    index = WEEKDAY_CODES.index(weekday)
    gender = WEEKDAY_GENDERS[index]
    name = WEEKDAYS_ACCUSATIVE[index]
    if ordinal == -1:
        last = {MASCULINE: "последний", FEMININE: "последнюю", NEUTER: "последнее"}[gender]
        return f"в {last} {name} месяца"
    every, suffix = {
        MASCULINE: ("каждый", "й"),
        FEMININE: ("каждую", "ю"),
        NEUTER: ("каждое", "е"),
    }[gender]
    return f"{every} {ordinal}-{suffix} {name} месяца"


def _yearly_phrase(parts: dict[str, str], start: datetime) -> str:
    month = _first_int(parts.get("BYMONTH")) or start.month
    day = _first_int(parts.get("BYMONTHDAY")) or start.day
    return f"каждый год {day} {MONTHS_GENITIVE[month - 1]}"


def _limit_suffix(parts: dict[str, str], reference: date | None) -> str:
    until = parts.get("UNTIL", "")
    if len(until) >= 8 and until[:8].isdigit():
        end = date(int(until[:4]), int(until[4:6]), int(until[6:8]))
        label = f"{end.day} {MONTHS_GENITIVE[end.month - 1]}"
        if reference is not None and end.year != reference.year:
            label += f" {end.year}"
        return f", до {label}"
    count = _first_int(parts.get("COUNT"))
    if count:
        return f", {count_phrase(count, TIMES)}"
    return ""
