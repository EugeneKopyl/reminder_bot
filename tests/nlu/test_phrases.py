from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import yaml
from dateutil.rrule import rrulestr

from bot.domain.parsing import ParseResult, ParseStatus, ReminderParser
from bot.domain.reminders import DayPeriodDefaults, ReminderDraft
from bot.nlu import parse_reminder

CORPUS: dict[str, Any] = yaml.safe_load(
    (Path(__file__).parent / "phrases.yaml").read_text(encoding="utf-8")
)
TIMEZONE = ZoneInfo(CORPUS["timezone"])
CASES: list[dict[str, Any]] = CORPUS["cases"]
DURATION_UNITS = {"m": "minutes", "h": "hours", "d": "days"}

parser: ReminderParser = parse_reminder


def case_id(case: dict[str, Any]) -> str:
    return f"{case['phrase']} @ {case['now']}" if "now" in case else str(case["phrase"])


def parse_case(case: dict[str, Any]) -> tuple[ParseResult, datetime]:
    now = datetime.fromisoformat(case.get("now", CORPUS["now"])).replace(tzinfo=TIMEZONE)
    return parser(case["phrase"], now, DayPeriodDefaults()), now


def parse_duration(text: str) -> timedelta:
    return timedelta(**{DURATION_UNITS[text[-1]]: int(text[:-1])})


def expected_fields(case: dict[str, Any]) -> dict[str, object]:
    fields: dict[str, object] = {
        "status": case.get("status", ParseStatus.OK.value),
        "text": case.get("text", ""),
    }
    if fields["status"] != ParseStatus.OK.value:
        return fields
    return fields | {
        "kind": case.get("kind", "once"),
        "start": datetime.fromisoformat(case["start"]),
        "rrule": case.get("rrule"),
        "interval": parse_duration(case["interval"]) if "interval" in case else None,
        "tags": case.get("tags", []),
        "priority": case.get("priority", "normal"),
        "pre_offsets": [parse_duration(offset) for offset in case.get("pre_offsets", [])],
        "nagging": case.get("nagging", False),
        "alternatives": case.get("alternatives", []),
    }


def actual_fields(result: ParseResult) -> dict[str, object]:
    fields: dict[str, object] = {"status": result.status.value, "text": result.text}
    draft = result.draft
    if draft is None:
        return fields
    schedule = draft.schedule
    return fields | {
        "kind": schedule.kind.value,
        "start": schedule.start,
        "rrule": schedule.rrule,
        "interval": schedule.interval_after_done,
        "tags": list(draft.tags),
        "priority": draft.priority.name.lower(),
        "pre_offsets": list(draft.pre_offsets),
        "nagging": draft.nagging is not None,
        "alternatives": [alternative.label for alternative in result.alternatives],
    }


def all_drafts(result: ParseResult) -> list[ReminderDraft]:
    drafts = [alternative.draft for alternative in result.alternatives]
    return [result.draft, *drafts] if result.draft is not None else drafts


@pytest.mark.parametrize("case", CASES, ids=case_id)
def test_phrase(case: dict[str, Any]) -> None:
    result, _ = parse_case(case)

    assert actual_fields(result) == expected_fields(case)


@pytest.mark.parametrize("case", CASES, ids=case_id)
def test_every_reading_starts_in_the_future(case: dict[str, Any]) -> None:
    result, now = parse_case(case)

    for draft in all_drafts(result):
        assert draft.schedule.start > now.replace(tzinfo=None)
        assert draft.schedule.start.tzinfo is None


@pytest.mark.parametrize("case", CASES, ids=case_id)
def test_rrule_first_occurrence_is_start(case: dict[str, Any]) -> None:
    result, _ = parse_case(case)

    for draft in all_drafts(result):
        schedule = draft.schedule
        if schedule.rrule is not None:
            assert rrulestr(schedule.rrule, dtstart=schedule.start)[0] == schedule.start


def test_corpus_is_large_enough() -> None:
    assert len(CASES) >= 150


def test_overlong_input_is_rejected() -> None:
    now = datetime(2026, 10, 22, 15, tzinfo=TIMEZONE)

    result = parser("завтра в 9 " + "очень " * 100, now, DayPeriodDefaults())

    assert result.status is ParseStatus.NOT_UNDERSTOOD


def test_custom_day_periods_are_respected() -> None:
    now = datetime(2026, 10, 22, 15, tzinfo=TIMEZONE)
    periods = DayPeriodDefaults(evening=datetime(2026, 1, 1, 20, 30).time())

    result = parser("вечером позвонить", now, periods)

    assert result.draft is not None
    assert result.draft.schedule.start == datetime(2026, 10, 22, 20, 30)
