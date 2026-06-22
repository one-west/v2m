from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from sqlmodel import Session, SQLModel, create_engine

from app.core.paths import get_db_path


def get_engine(db_path: Optional[Path] = None):
    path = db_path or get_db_path()
    return create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})


def init_db(engine) -> None:
    SQLModel.metadata.create_all(engine)


@contextmanager
def session_scope(engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session
