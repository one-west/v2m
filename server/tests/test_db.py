import sqlite3

from sqlmodel import Session

from app.store import db as db_module
from app.store import repo


def _make_pre_meta_db(path) -> None:
    """Create a `recording` table as it existed BEFORE the `meta` column was added."""
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE recording ("
        "id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL, "
        "duration_sec INTEGER, audio_path TEXT NOT NULL, status TEXT NOT NULL, "
        "error TEXT, transcript JSON)"
    )
    # status is stored as the enum NAME (SQLAlchemy Enum default), e.g. 'DONE'.
    con.execute(
        "INSERT INTO recording (id, title, created_at, audio_path, status) "
        "VALUES ('old1', '옛회의', '2026-06-20T00:00:00+00:00', '/a.webm', 'DONE')"
    )
    con.commit()
    con.close()


def test_init_db_adds_missing_meta_column(tmp_path):
    db_path = tmp_path / "old.db"
    _make_pre_meta_db(db_path)
    engine = db_module.get_engine(db_path)

    db_module.init_db(engine)  # forward-only migration must add `meta`

    with Session(engine) as s:
        rows = repo.list_recordings(s)  # the exact query that 500'd before the fix
        assert len(rows) == 1
        assert rows[0].meta is None
        repo.update_recording(s, "old1", meta={"location": "A"})
        assert repo.get_recording(s, "old1").meta == {"location": "A"}


def test_init_db_idempotent_on_current_schema(tmp_path):
    db_path = tmp_path / "new.db"
    engine = db_module.get_engine(db_path)
    db_module.init_db(engine)
    db_module.init_db(engine)  # second run must not error (meta already present)
    with Session(engine) as s:
        assert repo.list_recordings(s) == []
