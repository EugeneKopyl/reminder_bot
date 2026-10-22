"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-22 15:51:37.441462
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("timezone_confirmed", sa.Boolean(), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=True),
        sa.Column("key_version", sa.Integer(), nullable=False),
        sa.Column("privacy_mode", sa.String(length=32), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_active_on", sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "reminders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("dtstart_local", sa.DateTime(), nullable=False),
        sa.Column("tz", sa.String(length=64), nullable=True),
        sa.Column("rrule", sa.String(length=512), nullable=True),
        sa.Column("exdates", sa.JSON(), nullable=True),
        sa.Column("interval_after_done", sa.Integer(), nullable=True),
        sa.Column("pre_offsets", sa.JSON(), nullable=False),
        sa.Column("nag_interval", sa.Integer(), nullable=True),
        sa.Column("nag_max", sa.Integer(), nullable=True),
        sa.Column("priority", sa.SmallInteger(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("card_message_id", sa.BigInteger(), nullable=True),
        sa.Column("payload_ct", sa.LargeBinary(), nullable=True),
        sa.Column("payload_key_version", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("reminders", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_reminders_user_id"), ["user_id"], unique=False)

    op.create_table(
        "usage",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("voice_count", sa.Integer(), nullable=False),
        sa.Column("voice_seconds", sa.Integer(), nullable=False),
        sa.Column("imports", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "day"),
    )
    op.create_table(
        "occurrences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reminder_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("planned_at", sa.DateTime(), nullable=False),
        sa.Column("fire_at", sa.DateTime(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("snooze_count", sa.Integer(), nullable=False),
        sa.Column("nag_count", sa.Integer(), nullable=False),
        sa.Column("sent_message_id", sa.BigInteger(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("done_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["reminder_id"], ["reminders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("occurrences", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_occurrences_reminder_id"), ["reminder_id"], unique=False
        )
        batch_op.create_index("ix_occurrences_state_fire_at", ["state", "fire_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("occurrences", schema=None) as batch_op:
        batch_op.drop_index("ix_occurrences_state_fire_at")
        batch_op.drop_index(batch_op.f("ix_occurrences_reminder_id"))

    op.drop_table("occurrences")
    op.drop_table("usage")
    with op.batch_alter_table("reminders", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_reminders_user_id"))

    op.drop_table("reminders")
    op.drop_table("users")
