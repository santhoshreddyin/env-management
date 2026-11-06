"""Run Alembic migrations programmatically (used on startup and by the seed CLI)."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.config import settings
from app.database import engine

BACKEND_DIR = Path(__file__).resolve().parent.parent


def alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    return cfg


def run_migrations() -> None:
    cfg = alembic_config()
    tables = set(inspect(engine).get_table_names())
    # Databases created by the first version (tables auto-created, no Alembic) start at 0001.
    if "environments" in tables and "alembic_version" not in tables:
        command.stamp(cfg, "0001")
    command.upgrade(cfg, "head")
