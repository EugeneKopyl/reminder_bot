from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from bot.telegram.periods import ListPeriod, period_window
from bot.telegram.timezones import resolve_timezone, utc_offset_label

MOSCOW = ZoneInfo("Europe/Moscow")
NOW = datetime(2026, 10, 22, 15, 30, tzinfo=MOSCOW)


def test_day_window_is_local_midnight_to_midnight() -> None:
    window = period_window(ListPeriod.DAY, 1, NOW)

    assert window.start == datetime(2026, 10, 23, tzinfo=MOSCOW)
    assert window.end == datetime(2026, 10, 24, tzinfo=MOSCOW)


def test_week_window_starts_on_monday() -> None:
    window = period_window(ListPeriod.WEEK, -1, NOW)

    assert window.start == datetime(2026, 10, 12, tzinfo=MOSCOW)
    assert window.end == datetime(2026, 10, 19, tzinfo=MOSCOW)


def test_month_window_crosses_year_boundary() -> None:
    window = period_window(ListPeriod.MONTH, 3, NOW)

    assert window.start == datetime(2027, 1, 1, tzinfo=MOSCOW)
    assert window.end == datetime(2027, 2, 1, tzinfo=MOSCOW)


def test_all_period_has_no_window() -> None:
    with pytest.raises(ValueError, match="no time window"):
        period_window(ListPeriod.ALL, 0, NOW)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("europe/berlin", "Europe/Berlin"),
        (" Asia/Novosibirsk ", "Asia/Novosibirsk"),
        ("Москва", "Europe/Moscow"),
        ("Atlantis", None),
    ],
)
def test_resolve_timezone(text: str, expected: str | None) -> None:
    assert resolve_timezone(text) == expected


def test_utc_offset_label() -> None:
    assert utc_offset_label("Europe/Moscow", NOW) == "UTC+3"
    assert utc_offset_label("Asia/Kolkata", NOW) == "UTC+5:30"
    assert utc_offset_label("UTC", NOW) == "UTC"
