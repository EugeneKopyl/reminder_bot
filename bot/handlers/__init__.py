from aiogram import Router

from bot.handlers import cards, fallback, lists, notifications, reminders, start


def build_router() -> Router:
    router = Router(name="root")
    router.include_routers(
        start.router,
        lists.router,
        notifications.router,
        cards.router,
        reminders.router,
        fallback.router,
    )
    return router
