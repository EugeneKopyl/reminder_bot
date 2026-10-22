from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from dateutil.rrule import rrule, rruleset, rrulestr

from bot.domain.reminders import Schedule, ScheduleKind

DST_MARGIN = timedelta(hours=3)
MAX_EXPANDED_FIRES = 2000


def to_utc(local: datetime, tz: ZoneInfo) -> datetime:
    return local.replace(tzinfo=tz, fold=0).astimezone(UTC)


def to_local(instant: datetime, tz: ZoneInfo) -> datetime:
    return instant.astimezone(tz).replace(tzinfo=None)


def next_fire_after(schedule: Schedule, tz: ZoneInfo, after: datetime) -> datetime | None:
    best: datetime | None = None
    for local in _local_fires_from(schedule, to_local(after, tz) - DST_MARGIN):
        if best is not None and local > to_local(best, tz) + DST_MARGIN:
            break
        fire = to_utc(local, tz)
        if fire > after and (best is None or fire < best):
            best = fire
    return best


def fires_between(
    schedule: Schedule, tz: ZoneInfo, start: datetime, end: datetime
) -> list[datetime]:
    fires: set[datetime] = set()
    local_end = to_local(end, tz) + DST_MARGIN
    for local in _local_fires_from(schedule, to_local(start, tz) - DST_MARGIN):
        if local > local_end or len(fires) >= MAX_EXPANDED_FIRES:
            break
        fire = to_utc(local, tz)
        if start <= fire < end:
            fires.add(fire)
    return sorted(fires)


def last_fire_between(
    schedule: Schedule, tz: ZoneInfo, after: datetime, until: datetime
) -> datetime | None:
    if schedule.kind is not ScheduleKind.RRULE or schedule.rrule is None:
        fire = to_utc(schedule.start, tz)
        return fire if after < fire <= until else None
    rule = _parse_rule(schedule.rrule, schedule.start)
    local = rule.before(to_local(until, tz) + DST_MARGIN, inc=True)
    while local is not None:
        fire = to_utc(local, tz)
        if fire <= after:
            return None
        if fire <= until:
            return fire
        local = rule.before(local)
    return None


def _local_fires_from(schedule: Schedule, local_from: datetime) -> Iterator[datetime]:
    if schedule.kind is ScheduleKind.RRULE and schedule.rrule is not None:
        yield from _parse_rule(schedule.rrule, schedule.start).xafter(local_from, inc=True)
    elif schedule.start >= local_from:
        yield schedule.start


@lru_cache(maxsize=1024)
def _parse_rule(rule: str, start: datetime) -> rrule | rruleset:
    return rrulestr(rule, dtstart=start)
