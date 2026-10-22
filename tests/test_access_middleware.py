from aiogram.types import User

from bot.middlewares.access import AccessMiddleware


def make_user(user_id: int) -> User:
    return User(id=user_id, is_bot=False, first_name="Test")


def test_everyone_is_allowed_without_whitelist() -> None:
    middleware = AccessMiddleware(frozenset())

    assert middleware.is_allowed(make_user(1))
    assert middleware.is_allowed(None)


def test_whitelist_filters_users() -> None:
    middleware = AccessMiddleware(frozenset({1}))

    assert middleware.is_allowed(make_user(1))
    assert not middleware.is_allowed(make_user(2))
    assert not middleware.is_allowed(None)
