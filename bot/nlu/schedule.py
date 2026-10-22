import calendar
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta

from dateutil.relativedelta import relativedelta
from dateutil.rrule import rrulestr

from bot.domain.reminders import DayPeriodDefaults, Schedule, ScheduleKind
from bot.nlu.facts import (
    AfterCompletionFact,
    CalendarDateFact,
    ClockFact,
    CountFact,
    DateFact,
    DayOffsetFact,
    DayPeriod,
    Duration,
    Fact,
    FrequencyFact,
    HourWindowFact,
    MonthDayFact,
    MonthDaySetFact,
    PeriodFact,
    ShiftFact,
    StartFact,
    Unit,
    UntilFact,
    WeekdayFact,
    WeekdaySetFact,
)
from bot.nlu.vocabulary import WEEKDAY_CODES

RRULE_FREQUENCIES = {
    Unit.MINUTE: "MINUTELY",
    Unit.HOUR: "HOURLY",
    Unit.DAY: "DAILY",
    Unit.WEEK: "WEEKLY",
    Unit.MONTH: "MONTHLY",
    Unit.YEAR: "YEARLY",
}
APPROXIMATE_DAYS = {Unit.WEEK: 7, Unit.MONTH: 30, Unit.YEAR: 365}
SEARCH_YEARS = 9


@dataclass(frozen=True, slots=True)
class Reading:
    label: str
    schedule: Schedule


@dataclass(frozen=True, slots=True)
class Resolution:
    schedule: Schedule
    alternatives: tuple[Reading, ...] = ()


@dataclass(frozen=True, slots=True)
class Moment:
    now: datetime
    periods: DayPeriodDefaults

    @property
    def today(self) -> date:
        return self.now.date()


@dataclass(frozen=True, slots=True)
class Anchor:
    day: date
    roll: Callable[[date], date] | None = None


@dataclass(frozen=True, slots=True)
class FactIndex:
    clocks: list[ClockFact] = field(default_factory=list)
    periods: list[DayPeriod] = field(default_factory=list)
    dates: list[DateFact] = field(default_factory=list)
    shifts: list[ShiftFact] = field(default_factory=list)
    completions: list[AfterCompletionFact] = field(default_factory=list)
    frequencies: list[FrequencyFact] = field(default_factory=list)
    weekday_sets: list[WeekdaySetFact] = field(default_factory=list)
    month_day_sets: list[MonthDaySetFact] = field(default_factory=list)
    windows: list[HourWindowFact] = field(default_factory=list)
    untils: list[UntilFact] = field(default_factory=list)
    starts: list[StartFact] = field(default_factory=list)
    counts: list[CountFact] = field(default_factory=list)

    @classmethod
    def build(cls, facts: Iterable[Fact]) -> "FactIndex":
        index = cls()
        for fact in facts:
            index.add(fact)
        return index

    def add(self, fact: Fact) -> None:
        match fact:
            case ClockFact():
                self.clocks.append(fact)
            case PeriodFact():
                self.periods.append(fact.period)
            case CalendarDateFact() | DayOffsetFact() | MonthDayFact() | WeekdayFact():
                self.dates.append(fact)
            case ShiftFact():
                self.shifts.append(fact)
            case AfterCompletionFact():
                self.completions.append(fact)
            case FrequencyFact():
                self.frequencies.append(fact)
            case WeekdaySetFact():
                self.weekday_sets.append(fact)
            case MonthDaySetFact():
                self.month_day_sets.append(fact)
            case HourWindowFact():
                self.windows.append(fact)
            case UntilFact():
                self.untils.append(fact)
            case StartFact():
                self.starts.append(fact)
            case CountFact():
                self.counts.append(fact)

    @property
    def period(self) -> DayPeriod | None:
        return self.periods[0] if self.periods else None

    @property
    def settled_clocks(self) -> list[ClockFact]:
        period = self.period
        if period is None:
            return list(self.clocks)
        return [clock.in_period(period) if clock.ambiguous else clock for clock in self.clocks]

    @property
    def calendar_dates(self) -> list[CalendarDateFact]:
        return [fact for fact in self.dates if isinstance(fact, CalendarDateFact)]

    @property
    def weekday_dates(self) -> list[WeekdayFact]:
        return [fact for fact in self.dates if isinstance(fact, WeekdayFact)]

    def has_explicit_recurrence(self, *, yearly_hint: bool) -> bool:
        if self.frequencies or self.weekday_sets or self.month_day_sets or self.windows:
            return True
        return yearly_hint and bool(self.calendar_dates)

    def is_recurring(self, *, yearly_hint: bool) -> bool:
        if self.has_explicit_recurrence(yearly_hint=yearly_hint):
            return True
        return len(self.clocks) > 1 or len(self.weekday_dates) > 1


@dataclass(frozen=True, slots=True)
class RuleSpec:
    unit: Unit
    interval: int = 1
    weekdays: tuple[int, ...] = ()
    weekday_ordinal: int | None = None
    month_days: tuple[int, ...] = ()
    months: tuple[int, ...] = ()
    times: tuple[time, ...] = ()
    until: date | None = None
    count: int | None = None

    @property
    def needs_set_positions(self) -> bool:
        return len(self.time_grid) != len(set(self.times))

    @property
    def time_grid(self) -> list[time]:
        hours = sorted({moment.hour for moment in self.times})
        minutes = sorted({moment.minute for moment in self.times})
        return [time(hour, minute) for hour in hours for minute in minutes]

    def render(self) -> str:
        parts = [f"FREQ={RRULE_FREQUENCIES[self.unit]}"]
        if self.interval > 1:
            parts.append(f"INTERVAL={self.interval}")
        if self.weekdays:
            prefix = "" if self.weekday_ordinal is None else str(self.weekday_ordinal)
            codes = (prefix + WEEKDAY_CODES[weekday] for weekday in sorted(self.weekdays))
            parts.append("BYDAY=" + ",".join(codes))
        if self.month_days:
            ordered = sorted(self.month_days, key=lambda day: (day < 0, day))
            parts.append("BYMONTHDAY=" + ",".join(map(str, ordered)))
        if self.months:
            parts.append("BYMONTH=" + ",".join(map(str, sorted(self.months))))
        if self.times:
            parts.append(
                "BYHOUR=" + ",".join(str(hour) for hour in sorted({t.hour for t in self.times}))
            )
            parts.append(
                "BYMINUTE=" + ",".join(str(m) for m in sorted({t.minute for t in self.times}))
            )
            if self.needs_set_positions:
                grid = self.time_grid
                positions = (grid.index(moment) + 1 for moment in sorted(set(self.times)))
                parts.append("BYSETPOS=" + ",".join(map(str, positions)))
        if self.until is not None:
            parts.append(f"UNTIL={self.until:%Y%m%d}T235959")
        if self.count is not None:
            parts.append(f"COUNT={self.count}")
        return ";".join(parts)


def resolve_schedule(
    facts: Sequence[Fact], now: datetime, periods: DayPeriodDefaults, *, yearly_hint: bool
) -> Resolution | None:
    index = FactIndex.build(facts)
    moment = Moment(now.replace(tzinfo=None), periods)
    if index.completions:
        return resolve_after_completion(index, moment)
    if index.is_recurring(yearly_hint=yearly_hint):
        return resolve_recurring(index, moment, yearly_hint=yearly_hint)
    return resolve_once(index, moment)


def resolve_once(index: FactIndex, moment: Moment) -> Resolution | None:
    anchor: Anchor | None
    if index.shifts:
        durations = index.shifts[0].durations
        if any(duration.unit.is_sub_daily for duration in durations):
            exact = truncate(moment.now + to_relativedelta(durations))
            return Resolution(Schedule(ScheduleKind.ONCE, exact))
        anchor = Anchor(moment.today + to_relativedelta(durations))
    else:
        anchor = first_anchor(index, moment.today)
    clocks = index.settled_clocks
    if clocks and clocks[0].ambiguous:
        return resolve_ambiguous_once(clocks[0], anchor or today_anchor(moment), moment)
    time_of_day = explicit_time(index, moment.periods)
    if anchor is None:
        if time_of_day is None:
            return None
        anchor = today_anchor(moment)
    if time_of_day is None:
        time_of_day = default_time(anchor.day, moment)
    start = place(anchor, time_of_day, moment)
    return Resolution(Schedule(ScheduleKind.ONCE, start)) if start is not None else None


def resolve_ambiguous_once(clock: ClockFact, anchor: Anchor, moment: Moment) -> Resolution | None:
    early, late = time(clock.hour, clock.minute), time(clock.hour + 12, clock.minute)
    if anchor.day == moment.today:
        upcoming = sorted(
            candidate
            for candidate in (
                datetime.combine(anchor.day, early),
                datetime.combine(anchor.day, late),
            )
            if candidate > moment.now
        )
        if upcoming:
            chosen = upcoming[0]
        elif anchor.roll is not None:
            chosen = datetime.combine(anchor.roll(anchor.day), preferred_time(clock))
        else:
            return None
    else:
        chosen = datetime.combine(anchor.day, preferred_time(clock))
    other_time = late if chosen.time() == early else early
    other: datetime | None = datetime.combine(chosen.date(), other_time)
    if other is not None and other <= moment.now:
        other = datetime.combine(anchor.roll(chosen.date()), other_time) if anchor.roll else None
    alternatives: tuple[Reading, ...] = ()
    if other is not None:
        alternatives = (
            Reading(alternative_label(other, chosen, moment), Schedule(ScheduleKind.ONCE, other)),
        )
    return Resolution(Schedule(ScheduleKind.ONCE, chosen), alternatives)


def resolve_after_completion(index: FactIndex, moment: Moment) -> Resolution:
    durations = index.completions[0].durations
    interval = sum((to_timedelta(duration) for duration in durations), timedelta())
    if any(duration.unit.is_sub_daily for duration in durations):
        start = truncate(moment.now + interval)
    else:
        day = moment.today + to_relativedelta(durations)
        start = datetime.combine(
            day, explicit_time(index, moment.periods, prefer=True) or moment.periods.date_only
        )
    return Resolution(Schedule(ScheduleKind.AFTER_COMPLETION, start, interval_after_done=interval))


def resolve_recurring(index: FactIndex, moment: Moment, *, yearly_hint: bool) -> Resolution | None:
    spec, lower_bound = recurrence_spec(index, moment, yearly_hint=yearly_hint)
    if spec is None:
        return None
    clocks = index.settled_clocks
    alternative_spec: RuleSpec | None = None
    if (
        len(clocks) == 1
        and clocks[0].ambiguous
        and not spec.unit.is_sub_daily
        and not index.windows
    ):
        clock = clocks[0]
        chosen = preferred_time(clock)
        other = time(clock.hour if chosen.hour != clock.hour else clock.hour + 12, clock.minute)
        spec = fit_set_positions(replace(spec, times=(chosen,)))
        alternative_spec = fit_set_positions(replace(spec, times=(other,)))
    start = first_occurrence(spec, moment, lower_bound)
    if start is None:
        return None
    schedule = Schedule(ScheduleKind.RRULE, start, rrule=spec.render())
    alternatives: tuple[Reading, ...] = ()
    if alternative_spec is not None:
        alternative_start = first_occurrence(alternative_spec, moment, lower_bound)
        if alternative_start is not None:
            alternative = Schedule(
                ScheduleKind.RRULE, alternative_start, rrule=alternative_spec.render()
            )
            alternatives = (Reading(f"{alternative_spec.times[0]:%H:%M}", alternative),)
    return Resolution(schedule, alternatives)


def recurrence_spec(
    index: FactIndex, moment: Moment, *, yearly_hint: bool
) -> tuple[RuleSpec | None, date | None]:
    unit, interval = recurrence_unit(index, yearly_hint=yearly_hint)
    weekdays = unique(
        [
            *(day for fact in index.weekday_sets for day in fact.weekdays),
            *(fact.weekday for fact in index.weekday_dates),
        ]
    )
    ordinal = next((fact.ordinal for fact in index.weekday_sets if fact.ordinal is not None), None)
    if ordinal is not None and unit not in (Unit.MONTH, Unit.YEAR):
        unit, interval = Unit.MONTH, 1
    if unit is Unit.DAY and weekdays:
        unit = Unit.WEEK
    month_days = [day for fact in index.month_day_sets for day in fact.days]
    months: list[int] = []
    lower_bounds = [anchor_for(fact.target, moment.today).day for fact in index.starts]
    for fact in index.dates:
        if isinstance(fact, CalendarDateFact) and unit is Unit.YEAR:
            months.append(fact.month)
            month_days.append(fact.day)
        elif isinstance(fact, CalendarDateFact | MonthDayFact) and unit is Unit.MONTH:
            month_days.append(fact.day)
        elif not isinstance(fact, WeekdayFact):
            lower_bounds.append(anchor_for(fact, moment.today).day)
    until = anchor_for(index.untils[0].target, moment.today).day if index.untils else None
    count = index.counts[0].count if index.counts else None
    if count is None and not index.has_explicit_recurrence(yearly_hint=yearly_hint):
        count = max(1, len(index.clocks)) * max(1, len(weekdays))
    times = recurrence_times(index, unit, interval, moment.periods)
    if times is None:
        return None, None
    if index.windows and unit.is_sub_daily:
        unit, interval = (Unit.WEEK if weekdays else Unit.DAY), 1
    spec = RuleSpec(
        unit=unit,
        interval=interval,
        weekdays=tuple(weekdays),
        weekday_ordinal=ordinal,
        month_days=tuple(unique(month_days)),
        months=tuple(unique(months)),
        times=times,
        until=until,
        count=count,
    )
    return fit_set_positions(spec), max(lower_bounds, default=None)


def recurrence_unit(index: FactIndex, *, yearly_hint: bool) -> tuple[Unit, int]:
    if index.frequencies:
        frequency = index.frequencies[0]
        return frequency.unit, frequency.interval
    if any(fact.ordinal is not None for fact in index.weekday_sets):
        return Unit.MONTH, 1
    if index.weekday_sets or len(index.weekday_dates) > 1:
        return Unit.WEEK, 1
    if index.month_day_sets:
        return Unit.MONTH, 1
    if yearly_hint and index.calendar_dates:
        return Unit.YEAR, 1
    return Unit.DAY, 1


def recurrence_times(
    index: FactIndex, unit: Unit, interval: int, periods: DayPeriodDefaults
) -> tuple[time, ...] | None:
    if index.windows:
        window = index.windows[0]
        if not unit.is_sub_daily:
            return (time(window.start.hour, window.start.minute),)
        step = interval * (60 if unit is Unit.HOUR else 1)
        times = window_times(window, step)
        return times or None
    if unit.is_sub_daily:
        return ()
    clocks = index.settled_clocks
    if clocks:
        return tuple(unique(time(clock.hour, clock.minute) for clock in clocks))
    if index.period is not None:
        return (period_time(index.period, periods),)
    return (periods.date_only,)


def window_times(window: HourWindowFact, step: int) -> tuple[time, ...]:
    start = window.start.hour * 60 + window.start.minute
    end = window.end.hour * 60 + window.end.minute
    return tuple(time(minutes // 60, minutes % 60) for minutes in range(start, end + 1, step))


def fit_set_positions(spec: RuleSpec) -> RuleSpec:
    if spec.times and spec.needs_set_positions and spec.unit is Unit.WEEK and spec.interval == 1:
        return replace(spec, unit=Unit.DAY)
    return spec


def first_occurrence(spec: RuleSpec, moment: Moment, lower_bound: date | None) -> datetime | None:
    search_from, inclusive = moment.now, False
    if lower_bound is not None and datetime.combine(lower_bound, time()) > moment.now:
        search_from, inclusive = datetime.combine(lower_bound, time()), True
    search_spec = spec
    if spec.times or not spec.unit.is_sub_daily:
        dtstart = truncate(search_from)
        search_spec = replace(spec, interval=1)
    else:
        dtstart = truncate(search_from) + to_timedelta(Duration(spec.interval, spec.unit))
        search_from, inclusive = dtstart, True
    occurrence = rrulestr(search_spec.render(), dtstart=dtstart).after(search_from, inc=inclusive)
    return occurrence if isinstance(occurrence, datetime) else None


def first_anchor(index: FactIndex, today: date) -> Anchor | None:
    targets: list[DateFact] = [
        *index.dates,
        *(fact.target for fact in index.untils),
        *(fact.target for fact in index.starts),
    ]
    return anchor_for(targets[0], today) if targets else None


def anchor_for(target: DateFact, today: date) -> Anchor:
    match target:
        case DayOffsetFact(days=days):
            return Anchor(today + timedelta(days=days), next_day if days == 0 else None)
        case WeekdayFact():
            return Anchor(weekday_date(target, today), next_week)
        case CalendarDateFact(year=int() as year):
            return Anchor(date(year, target.month, target.day))
        case CalendarDateFact():
            return Anchor(
                next_calendar_date(target.month, target.day, today),
                annual_roll(target.month, target.day),
            )
        case MonthDayFact(day=day):
            return Anchor(next_month_day(day, today), monthly_roll(day))
        case _:
            return Anchor(period_end(target.unit, target.month, today))


def today_anchor(moment: Moment) -> Anchor:
    return Anchor(moment.today, next_day)


def next_day(day: date) -> date:
    return day + timedelta(days=1)


def next_week(day: date) -> date:
    return day + timedelta(days=7)


def annual_roll(month: int, day: int) -> Callable[[date], date]:
    return lambda current: next_calendar_date(month, day, current + timedelta(days=1))


def monthly_roll(day: int) -> Callable[[date], date]:
    return lambda current: next_month_day(day, current + timedelta(days=1))


def weekday_date(fact: WeekdayFact, today: date) -> date:
    if fact.next_week:
        return today + timedelta(days=7 - today.weekday() + fact.weekday)
    return today + timedelta(days=(fact.weekday - today.weekday()) % 7)


def next_calendar_date(month: int, day: int, start: date) -> date:
    for year in range(start.year, start.year + SEARCH_YEARS):
        if (
            day <= calendar.monthrange(year, month)[1]
            and (candidate := date(year, month, day)) >= start
        ):
            return candidate
    raise ValueError(f"no date {day}.{month} after {start}")


def next_month_day(day: int, start: date) -> date:
    year, month = start.year, start.month
    for _ in range(SEARCH_YEARS * 12):
        if (
            day <= calendar.monthrange(year, month)[1]
            and (candidate := date(year, month, day)) >= start
        ):
            return candidate
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    raise ValueError(f"no day {day} after {start}")


def period_end(unit: Unit, month: int | None, today: date) -> date:
    if unit is Unit.WEEK:
        return today + timedelta(days=6 - today.weekday())
    if unit is Unit.YEAR:
        return date(today.year, 12, 31)
    target_month = month or today.month
    year = today.year if target_month >= today.month else today.year + 1
    return date(year, target_month, calendar.monthrange(year, target_month)[1])


def place(anchor: Anchor, time_of_day: time, moment: Moment) -> datetime | None:
    candidate = datetime.combine(anchor.day, time_of_day)
    if candidate > moment.now:
        return candidate
    if anchor.roll is None:
        return None
    return datetime.combine(anchor.roll(anchor.day), time_of_day)


def explicit_time(
    index: FactIndex, periods: DayPeriodDefaults, *, prefer: bool = False
) -> time | None:
    clocks = index.settled_clocks
    if clocks:
        clock = clocks[0]
        return (
            preferred_time(clock) if prefer and clock.ambiguous else time(clock.hour, clock.minute)
        )
    if index.period is not None:
        return period_time(index.period, periods)
    return None


def default_time(day: date, moment: Moment) -> time:
    periods = moment.periods
    if day == moment.today:
        for slot in (periods.date_only, periods.afternoon, periods.evening, periods.night):
            if datetime.combine(day, slot) > moment.now:
                return slot
    return periods.date_only


def period_time(period: DayPeriod, periods: DayPeriodDefaults) -> time:
    return {
        DayPeriod.MORNING: periods.morning,
        DayPeriod.AFTERNOON: periods.afternoon,
        DayPeriod.EVENING: periods.evening,
        DayPeriod.NIGHT: periods.night,
    }[period]


def preferred_time(clock: ClockFact) -> time:
    hour = clock.hour + 12 if 1 <= clock.hour <= 5 else clock.hour
    return time(hour, clock.minute)


def alternative_label(alternative: datetime, chosen: datetime, moment: Moment) -> str:
    clock_text = f"{alternative:%H:%M}"
    if alternative.date() == chosen.date():
        return clock_text
    if alternative.date() == moment.today:
        return f"сегодня {clock_text}"
    if alternative.date() == next_day(moment.today):
        return f"завтра {clock_text}"
    return f"{alternative:%d.%m} {clock_text}"


def to_relativedelta(durations: Iterable[Duration]) -> relativedelta:
    total = relativedelta()
    for duration in durations:
        total += unit_relativedelta(duration)
    return total


def unit_relativedelta(duration: Duration) -> relativedelta:
    amount = duration.amount
    match duration.unit:
        case Unit.MINUTE:
            return relativedelta(minutes=amount)
        case Unit.HOUR:
            return relativedelta(hours=amount)
        case Unit.DAY:
            return relativedelta(days=amount)
        case Unit.WEEK:
            return relativedelta(weeks=amount)
        case Unit.MONTH:
            return relativedelta(months=amount)
        case Unit.YEAR:
            return relativedelta(years=amount)


def to_timedelta(duration: Duration) -> timedelta:
    if duration.unit is Unit.MINUTE:
        return timedelta(minutes=duration.amount)
    if duration.unit is Unit.HOUR:
        return timedelta(hours=duration.amount)
    return timedelta(days=duration.amount * APPROXIMATE_DAYS.get(duration.unit, 1))


def truncate(moment: datetime) -> datetime:
    return moment.replace(second=0, microsecond=0)


def unique[T](items: Iterable[T]) -> list[T]:
    return list(dict.fromkeys(items))
