from aiogram import Router

from bot.handlers import start


def build_router() -> Router:
    router = Router(name="root")
    router.include_router(start.router)
    return router
