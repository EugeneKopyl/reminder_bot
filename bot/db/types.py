from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, Dialect, Integer, String
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator[datetime]):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime cannot be stored as UTC")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC)


class Seconds(TypeDecorator[timedelta]):
    impl = Integer
    cache_ok = True

    def process_bind_param(self, value: timedelta | None, dialect: Dialect) -> int | None:
        return None if value is None else int(value.total_seconds())

    def process_result_value(self, value: int | None, dialect: Dialect) -> timedelta | None:
        return None if value is None else timedelta(seconds=value)


class SecondsList(TypeDecorator[list[timedelta]]):
    impl = JSON
    cache_ok = True

    def process_bind_param(self, value: list[timedelta] | None, dialect: Dialect) -> Any:
        return None if value is None else [int(item.total_seconds()) for item in value]

    def process_result_value(self, value: Any, dialect: Dialect) -> list[timedelta] | None:
        return None if value is None else [timedelta(seconds=item) for item in value]


class StrEnumType[E: StrEnum](TypeDecorator[E]):
    impl = String(32)
    cache_ok = True

    def __init__(self, enum_class: type[E]) -> None:
        super().__init__()
        self.enum_class = enum_class

    def process_bind_param(self, value: E | str | None, dialect: Dialect) -> str | None:
        return None if value is None else self.enum_class(value).value

    def process_result_value(self, value: str | None, dialect: Dialect) -> E | None:
        return None if value is None else self.enum_class(value)
