from pathlib import Path

from sqlmodel import Session

from app.store import repo
from app.store.models import RecordingStatus
from app.transcribe.base import Transcriber


def _friendly_error(exc: Exception) -> str:
    """Turn opaque download/network failures into an actionable Korean message."""
    text = str(exc)
    name = type(exc).__name__
    network = (
        "IncompleteRead" in text
        or "Connection broken" in text
        or "ConnectionError" in name
        or "ConnectionError" in text
        or "Timeout" in name
        or "ChunkedEncoding" in name
    )
    if network:
        return "모델 다운로드 또는 네트워크 연결이 중단되었습니다. 인터넷 연결을 확인하고 다시 시도해 주세요."
    return text


def run_transcription(rec_id: str, *, transcriber: Transcriber, engine) -> None:
    with Session(engine) as session:
        rec = repo.get_recording(session, rec_id)
        if rec is None:
            return
        repo.update_status(session, rec_id, RecordingStatus.TRANSCRIBING)
        audio_path = Path(rec.audio_path)
        language = rec.language

    def on_stage(stage: str) -> None:
        # Each update is a short write on its own session (no connection held during transcribe).
        with Session(engine) as s:
            repo.update_stage(s, rec_id, stage)

    try:
        result = transcriber.transcribe(audio_path, language=language, on_stage=on_stage)
    except Exception as exc:  # noqa: BLE001 - job must never raise
        with Session(engine) as session:
            repo.update_stage(session, rec_id, None)
            repo.update_status(session, rec_id, RecordingStatus.FAILED, error=_friendly_error(exc))
        return
    with Session(engine) as session:
        repo.set_transcript(session, rec_id, result.to_dict())  # also clears stage
