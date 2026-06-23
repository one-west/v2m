import pytest
from sqlmodel import Session

from app.jobs.queue import run_transcription
from app.store import db, repo
from app.store.models import RecordingStatus
from app.transcribe.fake import FakeTranscriber


@pytest.fixture
def engine(tmp_path):
    e = db.get_engine(tmp_path / "test.db")
    db.init_db(e)
    return e


def test_success_path_sets_done_with_transcript(engine):
    with Session(engine) as s:
        rec = repo.create_recording(s, title="X", audio_path="/x.webm")
        rec_id = rec.id

    run_transcription(rec_id, transcriber=FakeTranscriber(), engine=engine)

    with Session(engine) as s:
        updated = repo.get_recording(s, rec_id)
        assert updated.status == RecordingStatus.DONE
        assert updated.transcript["language"] == "ko"
        assert len(updated.transcript["segments"]) == 2


def test_failure_path_sets_failed_with_error(engine):
    class Boom:
        def transcribe(self, audio_path):
            raise RuntimeError("model exploded")

    with Session(engine) as s:
        rec = repo.create_recording(s, title="X", audio_path="/x.webm")
        rec_id = rec.id

    run_transcription(rec_id, transcriber=Boom(), engine=engine)

    with Session(engine) as s:
        updated = repo.get_recording(s, rec_id)
        assert updated.status == RecordingStatus.FAILED
        assert "model exploded" in updated.error
