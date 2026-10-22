from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from bot.domain.occurrences import ActionOutcome, Done, PlannedFire, SnoozeFor, StopSeries
from bot.domain.reminders import Priority, Schedule, ScheduleKind
from bot.telegram.formatting import (
    REMINDERS,
    action_result,
    count_phrase,
    describe_schedule,
    format_moment,
    render_period,
)
from bot.telegram.periods import ListPeriod, period_window

MOSCOW = ZoneInfo("Europe/Moscow")
TODAY = date(2026, 10, 22)


def at(hour: int, minute: int = 0, day: int = 22) -> datetime:
    return datetime(2026, 10, day, hour, minute)


def recurring(rule: str, start: datetime | None = None) -> Schedule:
    return Schedule(kind=ScheduleKind.RRULE, start=start or at(9), rrule=rule)


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (1, "1 напоминание"),
        (2, "2 напоминания"),
        (5, "5 напоминаний"),
        (11, "11 напоминаний"),
        (21, "21 напоминание"),
        (104, "104 напоминания"),
    ],
)
def test_count_phrase(count: int, expected: str) -> None:
    assert count_phrase(count, REMINDERS) == expected


def test_format_moment_shows_year_only_when_it_differs() -> None:
    assert format_moment(at(9), TODAY) == "чт, 22 окт, 09:00"
    assert format_moment(datetime(2027, 1, 4, 7, 5), TODAY) == "пн, 4 янв 2027, 07:05"


@pytest.mark.parametrize(
    ("schedule", "expected"),
    [
        (Schedule(ScheduleKind.ONCE, at(9, day=23)), "пт, 23 окт, 09:00 · однократно"),
        (recurring("FREQ=DAILY;BYHOUR=8,20;BYMINUTE=0"), "каждый день в 08:00 и 20:00"),
        (recurring("FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=9;BYMINUTE=0"), "по будням в 09:00"),
        (recurring("FREQ=WEEKLY;BYDAY=MO,WE", at(19)), "по понедельникам и средам в 19:00"),
        (
            recurring("FREQ=MONTHLY;BYDAY=2TU;BYHOUR=10;BYMINUTE=0"),
            "каждый 2-й вторник месяца в 10:00",
        ),
        (recurring("FREQ=MONTHLY;BYDAY=-1FR", at(18)), "в последнюю пятницу месяца в 18:00"),
        (recurring("FREQ=MONTHLY;BYMONTHDAY=-1"), "в последний день месяца в 09:00"),
        (recurring("FREQ=DAILY;INTERVAL=3"), "каждые 3 дня в 09:00"),
        (recurring("FREQ=YEARLY;BYMONTH=6;BYMONTHDAY=12"), "каждый год 12 июня в 09:00"),
        (
            recurring("FREQ=DAILY;BYHOUR=10,12,14,16,18,20;BYMINUTE=0"),
            "каждые 2 часа с 10:00 до 20:00",
        ),
        (recurring("FREQ=DAILY;UNTIL=20261130T235959Z"), "каждый день в 09:00, до 30 ноября"),
        (recurring("FREQ=WEEKLY;COUNT=5"), "по четвергам в 09:00, 5 раз"),
        (
            Schedule(ScheduleKind.AFTER_COMPLETION, at(9), interval_after_done=timedelta(days=3)),
            "через 3 дня после выполнения",
        ),
        (
            Schedule(ScheduleKind.AFTER_COMPLETION, at(9), interval_after_done=timedelta(weeks=1)),
            "через неделю после выполнения",
        ),
        (recurring("FREQ=SECONDLY"), "по особому расписанию"),
    ],
)
def test_describe_schedule(schedule: Schedule, expected: str) -> None:
    assert describe_schedule(schedule, TODAY) == expected


def test_render_day_lists_times_and_marks_without_text() -> None:
    now = datetime(2026, 10, 22, 8, 0, tzinfo=MOSCOW)
    window = period_window(ListPeriod.DAY, 0, now)
    fires = [
        PlannedFire(
            "b", at(18).replace(tzinfo=MOSCOW), recurring("FREQ=DAILY"), Priority.NORMAL, 5
        ),
        PlannedFire(
            "a",
            at(9).replace(tzinfo=MOSCOW),
            Schedule(ScheduleKind.ONCE, at(9)),
            Priority.IMPORTANT,
            4,
        ),
    ]

    rendered = render_period(window, fires, TODAY)

    assert rendered.splitlines() == [
        "📅 Сегодня · чт, 22 окт — 2 напоминания",
        "",
        "09:00 ❗",
        "18:00 🔁",
    ]


def test_render_empty_week() -> None:
    now = datetime(2026, 10, 22, 8, 0, tzinfo=MOSCOW)

    rendered = render_period(period_window(ListPeriod.WEEK, 1, now), [], TODAY)

    assert rendered == "🗓 Неделя · 26 окт – 1 ноя\n\nНичего не запланировано."


def test_action_result_rows() -> None:
    now = datetime(2026, 10, 22, 9, 12, tzinfo=MOSCOW)
    next_fire = datetime(2026, 10, 23, 9, 0, tzinfo=MOSCOW)

    assert action_result(Done(), ActionOutcome(True, next_fire), now) == [
        "✅ Выполнено в 09:12",
        "Далее: пт, 23 окт, 09:00",
    ]
    assert action_result(SnoozeFor(timedelta(minutes=15)), ActionOutcome(True), now) == [
        "⏰ Отложено до 09:27"
    ]
    assert action_result(StopSeries(), ActionOutcome(True, series_finished=True), now) == [
        "⏹ Серия остановлена"
    ]
