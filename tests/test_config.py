import pytest
from pydantic import ValidationError

from bot.config import Settings


@pytest.fixture(autouse=True)
def bot_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123:abc")


def load_settings() -> Settings:
    return Settings(_env_file=None)


def test_comma_separated_ids_are_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOWED_USER_IDS", "1, 2,,3")
    monkeypatch.setenv("ADMIN_IDS", "7")

    settings = load_settings()

    assert settings.allowed_user_ids == frozenset({1, 2, 3})
    assert settings.admin_ids == frozenset({7})


def test_ids_default_to_empty() -> None:
    assert load_settings().allowed_user_ids == frozenset()


def test_unknown_timezone_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEFAULT_TZ", "Mars/Olympus")

    with pytest.raises(ValidationError):
        load_settings()
