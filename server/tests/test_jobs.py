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
        def transcribe(self, audio_path, language=None, on_stage=None):
            raise RuntimeError("model exploded")

    with Session(engine) as s:
        rec = repo.create_recording(s, title="X", audio_path="/x.webm")
        rec_id = rec.id

    run_transcription(rec_id, transcriber=Boom(), engine=engine)

    with Session(engine) as s:
        updated = repo.get_recording(s, rec_id)
        assert updated.status == RecordingStatus.FAILED
        assert "model exploded" in updated.error


def test_passes_recording_language_to_transcriber(engine):
    with Session(engine) as s:
        rec = repo.create_recording(s, title="X", audio_path="/x.webm", language="en")
        rec_id = rec.id

    fake = FakeTranscriber()
    run_transcription(rec_id, transcriber=fake, engine=engine)

    assert fake.last_language == "en"


def test_wires_stage_callback_and_clears_stage_when_done(engine):
    with Session(engine) as s:
        rec_id = repo.create_recording(s, title="X", audio_path="/x.webm").id

    fake = FakeTranscriber()
    run_transcription(rec_id, transcriber=fake, engine=engine)

    assert fake.stages == ["transcribing"]  # on_stage callback was passed through
    with Session(engine) as s:
        got = repo.get_recording(s, rec_id)
        assert got.status == RecordingStatus.DONE
        assert got.stage is None  # cleared on completion


def test_network_error_becomes_friendly_message(engine):
    class Boom:
        def transcribe(self, audio_path, language=None, on_stage=None):
            raise RuntimeError("('Connection broken: IncompleteRead(100 read, 5 more expected)',)")

    with Session(engine) as s:
        rec_id = repo.create_recording(s, title="X", audio_path="/x.webm").id

    run_transcription(rec_id, transcriber=Boom(), engine=engine)

    with Session(engine) as s:
        got = repo.get_recording(s, rec_id)
        assert got.status == RecordingStatus.FAILED
        assert "네트워크" in got.error and "다시 시도" in got.error
