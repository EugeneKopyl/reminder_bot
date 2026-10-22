from datetime import datetime

from aiogram import F

from bot.domain.parsing import ParseResult, ReminderParser
from bot.domain.ports import Clock, ReminderService
from bot.domain.reminders import DayPeriodDefaults
from bot.telegram.timezones import local_now

plain_text = F.text & ~F.text.startswith("/")


async def parse_for_user(
    reminder_service: ReminderService,
    parse_reminder: ReminderParser,
    clock: Clock,
    user_id: int,
    text: str,
) -> tuple[datetime, DayPeriodDefaults, ParseResult]:
    profile = await reminder_service.ensure_user(user_id)
    now = local_now(clock, profile.timezone)
    return now, profile.day_periods, parse_reminder(text, now, profile.day_periods)
