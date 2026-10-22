from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ui_fakes import (
    FakeReminderService,
    FixedClock,
    make_bot,
    make_callback,
    make_message,
    make_state,
    parser_returning,
)

from bot.domain.occurrences import ActionOutcome, Done, PlannedFire, SnoozeUntil
from bot.domain.parsing import Alternative, ParseResult, ParseStatus
from bot.domain.ports import ReminderService
from bot.domain.reminders import Priority, ReminderDraft, Schedule, ScheduleKind
from bot.handlers.cards import choose_alternative
from bot.handlers.lists import list_by_menu
from bot.handlers.notifications import apply_notification_action, apply_snooze_time, ask_snooze_time
from bot.handlers.reminders import choose_quick_time, create_from_text
from bot.telegram.callbacks import (
    CardAction,
    CardCallback,
    NotificationAction,
    NotificationCallback,
    QuickTime,
    QuickTimeCallback,
)
from bot.telegram.states import PendingReminder

MOSCOW = ZoneInfo("Europe/Moscow")
TOMORROW_NINE = Schedule(ScheduleKind.ONCE, datetime(2026, 10, 23, 9, 0))
TOMORROW_SEVEN = Schedule(ScheduleKind.ONCE, datetime(2026, 10, 23, 7, 0))


async def test_text_creates_reminder_and_card() -> None:
    service = FakeReminderService()
    bot = make_bot(sent_message_id=77)
    draft = ReminderDraft(text="позвонить <маме>", schedule=TOMORROW_NINE)
    parser = parser_returning(ParseResult(ParseStatus.OK, draft.text, draft))
    reminder_service: ReminderService = service

    await create_from_text(
        make_message("завтра в 9 позвонить <маме>"),
        make_state(),
        bot,
        reminder_service,
        parser,
        FixedClock(),
    )

    assert service.created == [draft]
    assert service.cards == {"reminder-1": 77}
    card = bot.send_message.await_args.kwargs
    assert card["text"] == "🔔 позвонить &lt;маме&gt;"
    assert card["reply_parameters"].message_id == 10
    bot.set_message_reaction.assert_awaited_once()


async def test_missing_time_is_asked_and_quick_option_creates_reminder() -> None:
    service = FakeReminderService()
    bot = make_bot()
    state = make_state()
    parser = parser_returning(ParseResult(ParseStatus.NEEDS_TIME, "купить хлеб"))

    await create_from_text(make_message("купить хлеб"), state, bot, service, parser, FixedClock())

    assert await state.get_state() == PendingReminder.waiting_time.state
    assert service.created == []

    await choose_quick_time(
        make_callback("q:m"),
        QuickTimeCallback(option=QuickTime.TOMORROW_MORNING),
        state,
        bot,
        service,
        FixedClock(),
    )

    assert service.created == [ReminderDraft(text="купить хлеб", schedule=TOMORROW_NINE)]
    assert await state.get_state() is None


async def test_alternative_reading_replaces_schedule() -> None:
    service = FakeReminderService()
    bot = make_bot()
    state = make_state()
    draft = ReminderDraft(text="пробежка", schedule=TOMORROW_SEVEN)
    alternative = Alternative("19:00", ReminderDraft(text="пробежка", schedule=TOMORROW_NINE))
    parser = parser_returning(ParseResult(ParseStatus.OK, "пробежка", draft, (alternative,)))
    await create_from_text(make_message("в 7 пробежка"), state, bot, service, parser, FixedClock())

    await choose_alternative(
        make_callback("c:a:reminder-1:0"),
        CardCallback(action=CardAction.ALTERNATIVE, reminder_id="reminder-1", index=0),
        state,
        bot,
        service,
    )

    assert service.replaced == [("reminder-1", TOMORROW_NINE)]


async def test_done_replaces_notification_keyboard_with_result() -> None:
    next_fire = datetime(2026, 10, 23, 9, 0, tzinfo=MOSCOW)
    service = FakeReminderService(outcome=ActionOutcome(applied=True, next_fire_at=next_fire))
    bot = make_bot()

    await apply_notification_action(
        make_callback("n:d:5:0", message_id=60),
        NotificationCallback(action=NotificationAction.DONE, occurrence_id=5),
        bot,
        service,
        FixedClock(),
    )

    assert service.actions == [(5, Done())]
    markup = bot.edit_message_reply_markup.await_args.kwargs["reply_markup"]
    assert [row[0].text for row in markup.inline_keyboard] == [
        "✅ Выполнено в 09:00",
        "Далее: пт, 23 окт, 09:00",
    ]


async def test_stale_action_only_answers_callback() -> None:
    service = FakeReminderService(outcome=ActionOutcome(applied=False))
    bot = make_bot()

    await apply_notification_action(
        make_callback("n:d:5:0"),
        NotificationCallback(action=NotificationAction.DONE, occurrence_id=5),
        bot,
        service,
        FixedClock(),
    )

    bot.edit_message_reply_markup.assert_not_awaited()
    assert bot.answer_callback_query.await_args.kwargs["text"] == "Это напоминание уже обработано."


async def test_snooze_to_typed_time() -> None:
    service = FakeReminderService()
    bot = make_bot()
    state = make_state()
    in_forty_minutes = Schedule(ScheduleKind.ONCE, datetime(2026, 10, 22, 9, 40))
    parser = parser_returning(
        ParseResult(ParseStatus.OK, "", ReminderDraft(text="", schedule=in_forty_minutes))
    )

    await ask_snooze_time(
        make_callback("n:o:8:0", message_id=61),
        NotificationCallback(action=NotificationAction.OTHER, occurrence_id=8),
        state,
        bot,
    )
    await apply_snooze_time(
        make_message("через 40 минут"), state, bot, service, parser, FixedClock()
    )

    assert service.actions == [(8, SnoozeUntil(datetime(2026, 10, 22, 9, 40, tzinfo=MOSCOW)))]
    assert bot.edit_message_reply_markup.await_args.kwargs["message_id"] == 61
    assert await state.get_state() is None


async def test_today_menu_button_lists_fires_for_local_day() -> None:
    fire_at = datetime(2026, 10, 22, 18, 0, tzinfo=MOSCOW)
    service = FakeReminderService(
        fires=[PlannedFire("r", fire_at, TOMORROW_NINE, Priority.NORMAL, card_message_id=5)]
    )
    bot = make_bot()

    await list_by_menu(make_message("📅 Сегодня"), make_state(), bot, service, FixedClock())

    assert service.fire_windows == [
        (
            datetime(2026, 10, 22, tzinfo=MOSCOW),
            datetime(2026, 10, 22, tzinfo=MOSCOW) + timedelta(days=1),
        )
    ]
    text = bot.send_message.await_args.kwargs["text"]
    assert text.splitlines()[-1] == "18:00"
