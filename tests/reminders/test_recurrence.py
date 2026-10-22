from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from bot.domain.reminders import Schedule, ScheduleKind
from bot.scheduling.recurrence import (
    fires_between,
    last_fire_between,
    next_fire_after,
    to_utc,
)

BERLIN = ZoneInfo("Europe/Berlin")
MOSCOW = ZoneInfo("Europe/Moscow")


def daily(start: datetime, extra: str = "") -> Schedule:
    return Schedule(kind=ScheduleKind.RRULE, start=start, rrule=f"FREQ=DAILY{extra}")


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def test_nonexistent_local_time_is_shifted_forward() -> None:
    assert to_utc(datetime(2026, 3, 29, 2, 30), BERLIN) == utc(2026, 3, 29, 1, 30)


def test_ambiguous_local_time_uses_first_occurrence() -> None:
    assert to_utc(datetime(2026, 10, 25, 2, 30), BERLIN) == utc(2026, 10, 25, 0, 30)


def test_daily_schedule_keeps_wall_clock_across_spring_transition() -> None:
    schedule = daily(datetime(2026, 3, 27, 9, 0))

    fires = fires_between(schedule, BERLIN, utc(2026, 3, 28), utc(2026, 3, 31))

    assert fires == [utc(2026, 3, 28, 8), utc(2026, 3, 29, 7), utc(2026, 3, 30, 7)]


def test_daily_schedule_keeps_wall_clock_across_autumn_transition() -> None:
    schedule = daily(datetime(2026, 10, 24, 2, 30))

    fires = fires_between(schedule, BERLIN, utc(2026, 10, 24), utc(2026, 10, 27))

    assert fires == [utc(2026, 10, 24, 0, 30), utc(2026, 10, 25, 0, 30), utc(2026, 10, 26, 1, 30)]


def test_time_inside_spring_gap_fires_once_after_the_gap() -> None:
    schedule = daily(datetime(2026, 3, 28, 2, 30))

    fires = fires_between(schedule, BERLIN, utc(2026, 3, 29), utc(2026, 3, 30))

    assert fires == [utc(2026, 3, 29, 1, 30)]


def test_next_fire_for_once_schedule() -> None:
    schedule = Schedule(kind=ScheduleKind.ONCE, start=datetime(2026, 10, 23, 9, 0))

    assert next_fire_after(schedule, MOSCOW, utc(2026, 10, 22)) == utc(2026, 10, 23, 6)
    assert next_fire_after(schedule, MOSCOW, utc(2026, 10, 24)) is None


def test_next_fire_for_weekday_rule() -> None:
    schedule = Schedule(
        kind=ScheduleKind.RRULE,
        start=datetime(2026, 10, 22, 9, 0),
        rrule="FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=9;BYMINUTE=0",
    )

    friday = utc(2026, 10, 23, 6)
    monday = utc(2026, 10, 26, 6)
    assert next_fire_after(schedule, MOSCOW, utc(2026, 10, 22, 7)) == friday
    assert next_fire_after(schedule, MOSCOW, friday) == monday


def test_rule_with_until_is_exhausted() -> None:
    schedule = daily(datetime(2026, 10, 22, 9, 0), ";UNTIL=20261024T235959")

    assert next_fire_after(schedule, MOSCOW, utc(2026, 10, 24, 6)) is None


def test_monthly_second_tuesday() -> None:
    schedule = Schedule(
        kind=ScheduleKind.RRULE,
        start=datetime(2026, 10, 22, 10, 0),
        rrule="FREQ=MONTHLY;BYDAY=2TU",
    )

    assert next_fire_after(schedule, MOSCOW, utc(2026, 10, 22)) == utc(2026, 11, 10, 7)


def test_last_fire_between_returns_latest_past_fire() -> None:
    schedule = daily(datetime(2026, 10, 20, 9, 0))

    latest = last_fire_between(schedule, MOSCOW, utc(2026, 10, 20, 6), utc(2026, 10, 23, 7))

    assert latest == utc(2026, 10, 23, 6)


def test_last_fire_between_without_later_fire() -> None:
    schedule = daily(datetime(2026, 10, 20, 9, 0))

    assert last_fire_between(schedule, MOSCOW, utc(2026, 10, 23, 6), utc(2026, 10, 23, 7)) is None
