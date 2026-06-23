import pytest
from sqlmodel import Session

from app.store import db, repo
from app.store.models import RecordingStatus


@pytest.fixture
def engine(tmp_path):
    e = db.get_engine(tmp_path / "test.db")
    db.init_db(e)
    return e


def test_create_and_get(engine):
    with Session(engine) as s:
        rec = repo.create_recording(s, title="Standup", audio_path="/a/b.webm")
        assert rec.id
        assert rec.status == RecordingStatus.RECORDED
        fetched = repo.get_recording(s, rec.id)
        assert fetched.title == "Standup"


def test_list_newest_first(engine):
    with Session(engine) as s:
        a = repo.create_recording(s, title="A", audio_path="/a")
        b = repo.create_recording(s, title="B", audio_path="/b")
        ids = [r.id for r in repo.list_recordings(s)]
        assert ids[0] == b.id and ids[1] == a.id


def test_update_status_and_transcript(engine):
    with Session(engine) as s:
        rec = repo.create_recording(s, title="X", audio_path="/x")
        repo.update_status(s, rec.id, RecordingStatus.TRANSCRIBING)
        repo.set_transcript(s, rec.id, {"segments": [], "full_text": "hi", "language": "ko"})
        updated = repo.get_recording(s, rec.id)
        assert updated.status == RecordingStatus.DONE
        assert updated.transcript["full_text"] == "hi"


def test_failed_status_keeps_error(engine):
    with Session(engine) as s:
        rec = repo.create_recording(s, title="X", audio_path="/x")
        repo.update_status(s, rec.id, RecordingStatus.FAILED, error="boom")
        assert repo.get_recording(s, rec.id).error == "boom"


def test_delete(engine):
    with Session(engine) as s:
        rec = repo.create_recording(s, title="X", audio_path="/x")
        assert repo.delete_recording(s, rec.id) is True
        assert repo.get_recording(s, rec.id) is None
        assert repo.delete_recording(s, "missing") is False


def test_update_status_missing_id_raises(engine):
    from sqlmodel import Session
    with Session(engine) as s:
        with pytest.raises(ValueError):
            repo.update_status(s, "missing", RecordingStatus.DONE)


def test_set_transcript_missing_id_raises(engine):
    from sqlmodel import Session
    with Session(engine) as s:
        with pytest.raises(ValueError):
            repo.set_transcript(s, "missing", {"segments": [], "full_text": "", "language": "ko"})


def test_meta_defaults_none_and_roundtrips(engine):
    with Session(engine) as s:
        rec = repo.create_recording(s, title="X", audio_path="/x")
        assert rec.meta is None
        updated = repo.update_recording(
            s, rec.id, meta={"location": "회의실 A", "attendees": "홍길동, 김철수"}
        )
        assert updated.meta["location"] == "회의실 A"
        assert repo.get_recording(s, rec.id).meta["attendees"] == "홍길동, 김철수"


def test_update_recording_title_only_keeps_meta(engine):
    with Session(engine) as s:
        rec = repo.create_recording(s, title="X", audio_path="/x")
        repo.update_recording(s, rec.id, meta={"agenda": "Q3"})
        repo.update_recording(s, rec.id, title="새 제목")
        got = repo.get_recording(s, rec.id)
        assert got.title == "새 제목"
        assert got.meta == {"agenda": "Q3"}


def test_update_recording_missing_id_raises(engine):
    with Session(engine) as s:
        with pytest.raises(ValueError):
            repo.update_recording(s, "missing", title="x")
