from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum


class ListPeriod(StrEnum):
    DAY = "d"
    WEEK = "w"
    MONTH = "m"
    ALL = "a"


@dataclass(frozen=True, slots=True)
class PeriodWindow:
    period: ListPeriod
    start: datetime
    end: datetime


def period_window(period: ListPeriod, offset: int, now: datetime) -> PeriodWindow:
    today = now.date()
    if period is ListPeriod.DAY:
        first = today + timedelta(days=offset)
        last = first + timedelta(days=1)
    elif period is ListPeriod.WEEK:
        first = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
        last = first + timedelta(weeks=1)
    elif period is ListPeriod.MONTH:
        first = _shift_month(today.replace(day=1), offset)
        last = _shift_month(first, 1)
    else:
        raise ValueError(f"{period} has no time window")
    return PeriodWindow(period, _midnight(first, now), _midnight(last, now))


def _shift_month(first_day: date, months: int) -> date:
    year, month_index = divmod(first_day.year * 12 + first_day.month - 1 + months, 12)
    return date(year, month_index + 1, 1)


def _midnight(day: date, now: datetime) -> datetime:
    return datetime.combine(day, time(), tzinfo=now.tzinfo)
