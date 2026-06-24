from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.core.paths import get_db_path


def get_engine(db_path: Optional[Path] = None) -> Engine:
    path = db_path or get_db_path()
    return create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})


def init_db(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)
    _migrate_recording_columns(engine)


# Forward-only, idempotent column adds for tables that predate a new field.
# `create_all` only creates MISSING tables — it never alters an existing one —
# so a DB created before a column was added needs the column backfilled here.
# (Single-user local SQLite; no Alembic.) Maps model field -> SQLite DDL type.
_RECORDING_ADDED_COLUMNS = {"meta": "JSON", "language": "TEXT"}


def _migrate_recording_columns(engine: Engine) -> None:
    with engine.begin() as conn:
        existing = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(recording)")}
        for name, ddl_type in _RECORDING_ADDED_COLUMNS.items():
            if name not in existing:
                conn.exec_driver_sql(f"ALTER TABLE recording ADD COLUMN {name} {ddl_type}")


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session
