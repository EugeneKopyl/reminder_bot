from pathlib import Path
from typing import Annotated
from zoneinfo import available_timezones

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: SecretStr
    allowed_user_ids: Annotated[frozenset[int], NoDecode] = frozenset()
    admin_ids: Annotated[frozenset[int], NoDecode] = frozenset()
    database_path: Path = Path("data/bot.sqlite3")
    default_tz: str = "Europe/Moscow"
    log_level: str = "INFO"

    @field_validator("allowed_user_ids", "admin_ids", mode="before")
    @classmethod
    def split_comma_separated_ids(cls, value: object) -> object:
        if isinstance(value, str):
            return frozenset(int(part) for part in value.split(",") if part.strip())
        return value

    @field_validator("default_tz")
    @classmethod
    def ensure_known_timezone(cls, value: str) -> str:
        if value not in available_timezones():
            raise ValueError(f"unknown timezone: {value}")
        return value
