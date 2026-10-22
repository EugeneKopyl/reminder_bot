from pathlib import Path

from alembic import command
from alembic.config import Config

from bot.db.engine import sqlite_url

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def upgrade_database(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    config = Config(PROJECT_ROOT / "alembic.ini")
    config.set_main_option("sqlalchemy.url", sqlite_url(database_path).replace("%", "%%"))
    command.upgrade(config, "head")
