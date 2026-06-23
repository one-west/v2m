from pathlib import Path

from sqlmodel import Session

from app.store import repo
from app.store.models import RecordingStatus
from app.transcribe.base import Transcriber


def run_transcription(rec_id: str, *, transcriber: Transcriber, engine) -> None:
    with Session(engine) as session:
        rec = repo.get_recording(session, rec_id)
        if rec is None:
            return
        repo.update_status(session, rec_id, RecordingStatus.TRANSCRIBING)
        audio_path = Path(rec.audio_path)
    try:
        result = transcriber.transcribe(audio_path)
    except Exception as exc:  # noqa: BLE001 - job must never raise
        with Session(engine) as session:
            repo.update_status(session, rec_id, RecordingStatus.FAILED, error=str(exc))
        return
    with Session(engine) as session:
        repo.set_transcript(session, rec_id, result.to_dict())
