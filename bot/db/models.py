import secrets
import time
import uuid
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from bot.db.types import Seconds, SecondsList, StrEnumType, UtcDateTime
from bot.domain.occurrences import OccurrenceKind
from bot.domain.reminders import ScheduleKind


class UserStatus(StrEnum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    DELETED = "deleted"


class PrivacyMode(StrEnum):
    STANDARD = "standard"
    STRICT = "strict"


class ReminderState(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ReminderSource(StrEnum):
    CHAT = "chat"
    MINIAPP = "miniapp"
    IMPORT = "import"
    CALENDAR = "calendar"


class OccurrenceState(StrEnum):
    SCHEDULED = "scheduled"
    SENDING = "sending"
    SENT = "sent"
    DONE = "done"
    SKIPPED = "skipped"
    MISSED = "missed"
    CANCELLED = "cancelled"


PENDING_STATES = (OccurrenceState.SCHEDULED, OccurrenceState.SENDING)


def new_reminder_id() -> str:
    timestamp_ms = time.time_ns() // 1_000_000
    value = (
        (timestamp_ms & ((1 << 48) - 1)) << 80
        | 0x7 << 76
        | secrets.randbits(12) << 64
        | 0b10 << 62
        | secrets.randbits(62)
    )
    return str(uuid.UUID(int=value))


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    timezone: Mapped[str] = mapped_column(String(64))
    timezone_confirmed: Mapped[bool] = mapped_column(default=False)
    public_key: Mapped[bytes | None] = mapped_column(LargeBinary)
    key_version: Mapped[int] = mapped_column(Integer, default=0)
    privacy_mode: Mapped[PrivacyMode] = mapped_column(
        StrEnumType(PrivacyMode), default=PrivacyMode.STANDARD
    )
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[UserStatus] = mapped_column(StrEnumType(UserStatus), default=UserStatus.ACTIVE)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    last_active_on: Mapped[date | None]


class ReminderRow(Base):
    __tablename__ = "reminders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_reminder_id)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[ScheduleKind] = mapped_column(StrEnumType(ScheduleKind))
    dtstart_local: Mapped[datetime] = mapped_column(DateTime)
    tz: Mapped[str | None] = mapped_column(String(64))
    rrule: Mapped[str | None] = mapped_column(String(512))
    exdates: Mapped[list[str] | None] = mapped_column(JSON)
    interval_after_done: Mapped[timedelta | None] = mapped_column(Seconds)
    pre_offsets: Mapped[list[timedelta]] = mapped_column(SecondsList, default=list)
    nag_interval: Mapped[timedelta | None] = mapped_column(Seconds)
    nag_max: Mapped[int | None]
    priority: Mapped[int] = mapped_column(SmallInteger, default=0)
    state: Mapped[ReminderState] = mapped_column(
        StrEnumType(ReminderState), default=ReminderState.ACTIVE
    )
    card_message_id: Mapped[int | None] = mapped_column(BigInteger)
    payload_ct: Mapped[bytes | None] = mapped_column(LargeBinary)
    payload_key_version: Mapped[int | None]
    source: Mapped[ReminderSource] = mapped_column(
        StrEnumType(ReminderSource), default=ReminderSource.CHAT
    )
    source_ref: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime)

    user: Mapped[UserRow] = relationship(lazy="raise")


class OccurrenceRow(Base):
    __tablename__ = "occurrences"
    __table_args__ = (Index("ix_occurrences_state_fire_at", "state", "fire_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reminder_id: Mapped[str] = mapped_column(
        ForeignKey("reminders.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[OccurrenceKind] = mapped_column(
        StrEnumType(OccurrenceKind), default=OccurrenceKind.MAIN
    )
    planned_at: Mapped[datetime] = mapped_column(UtcDateTime)
    fire_at: Mapped[datetime] = mapped_column(UtcDateTime)
    state: Mapped[OccurrenceState] = mapped_column(
        StrEnumType(OccurrenceState), default=OccurrenceState.SCHEDULED
    )
    snooze_count: Mapped[int] = mapped_column(Integer, default=0)
    nag_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_message_id: Mapped[int | None] = mapped_column(BigInteger)
    sent_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    done_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    reminder: Mapped[ReminderRow] = relationship(lazy="raise")


class UsageRow(Base):
    __tablename__ = "usage"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(primary_key=True)
    voice_count: Mapped[int] = mapped_column(Integer, default=0)
    voice_seconds: Mapped[int] = mapped_column(Integer, default=0)
    imports: Mapped[int] = mapped_column(Integer, default=0)
