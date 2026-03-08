from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config


def run_migrations(database_url: str) -> None:
    config = Config(str(Path("alembic.ini").resolve()))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
