from datetime import datetime, timedelta
from functools import cache
from zoneinfo import ZoneInfo, available_timezones

from bot.domain.ports import Clock

CITY_TIMEZONES: tuple[tuple[str, str], ...] = (
    ("Калининград", "Europe/Kaliningrad"),
    ("Москва", "Europe/Moscow"),
    ("Самара", "Europe/Samara"),
    ("Екатеринбург", "Asia/Yekaterinburg"),
    ("Омск", "Asia/Omsk"),
    ("Новосибирск", "Asia/Novosibirsk"),
    ("Красноярск", "Asia/Krasnoyarsk"),
    ("Иркутск", "Asia/Irkutsk"),
    ("Якутск", "Asia/Yakutsk"),
    ("Владивосток", "Asia/Vladivostok"),
    ("Магадан", "Asia/Magadan"),
    ("Камчатка", "Asia/Kamchatka"),
    ("Минск", "Europe/Minsk"),
    ("Киев", "Europe/Kyiv"),
    ("Кишинёв", "Europe/Chisinau"),
    ("Тбилиси", "Asia/Tbilisi"),
    ("Ереван", "Asia/Yerevan"),
    ("Баку", "Asia/Baku"),
    ("Алматы", "Asia/Almaty"),
    ("Ташкент", "Asia/Tashkent"),
    ("Бишкек", "Asia/Bishkek"),
    ("Душанбе", "Asia/Dushanbe"),
)


def local_now(clock: Clock, timezone: str) -> datetime:
    return clock.now().astimezone(ZoneInfo(timezone))


def utc_offset_label(timezone: str, moment: datetime) -> str:
    offset = moment.astimezone(ZoneInfo(timezone)).utcoffset() or timedelta()
    total_minutes = int(offset.total_seconds() // 60)
    if total_minutes == 0:
        return "UTC"
    sign = "+" if total_minutes > 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    return f"UTC{sign}{hours}" + (f":{minutes:02d}" if minutes else "")


def timezone_label(timezone: str, moment: datetime) -> str:
    city = _city_by_zone().get(timezone, timezone)
    return f"{city} ({utc_offset_label(timezone, moment)})"


def resolve_timezone(text: str) -> str | None:
    candidate = text.strip().replace(" ", "_").casefold()
    return _zones_by_casefolded_name().get(candidate) or _zone_by_city().get(candidate)


@cache
def _zones_by_casefolded_name() -> dict[str, str]:
    return {zone.casefold(): zone for zone in available_timezones()}


@cache
def _zone_by_city() -> dict[str, str]:
    return {city.replace(" ", "_").casefold(): zone for city, zone in CITY_TIMEZONES}


@cache
def _city_by_zone() -> dict[str, str]:
    return {zone: city for city, zone in CITY_TIMEZONES}
