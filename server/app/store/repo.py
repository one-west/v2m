from typing import Optional

from sqlalchemy import text
from sqlmodel import Session, select

from app.store.models import Recording, RecordingStatus


def create_recording(session: Session, *, title: str, audio_path: str,
                     duration_sec: Optional[int] = None,
                     language: Optional[str] = None) -> Recording:
    rec = Recording(title=title, audio_path=audio_path, duration_sec=duration_sec,
                    language=language)
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


def get_recording(session: Session, rec_id: str) -> Optional[Recording]:
    return session.get(Recording, rec_id)


def list_recordings(session: Session) -> list[Recording]:
    stmt = select(Recording).order_by(Recording.created_at.desc(), text("rowid DESC"))
    return list(session.exec(stmt))


def update_status(session: Session, rec_id: str, status: RecordingStatus,
                  error: Optional[str] = None) -> Recording:
    rec = session.get(Recording, rec_id)
    if rec is None:
        raise ValueError(f"recording not found: {rec_id}")
    rec.status = status
    rec.error = error
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


def set_transcript(session: Session, rec_id: str, transcript: dict) -> Recording:
    rec = session.get(Recording, rec_id)
    if rec is None:
        raise ValueError(f"recording not found: {rec_id}")
    rec.transcript = transcript
    rec.status = RecordingStatus.DONE
    rec.error = None
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


def delete_recording(session: Session, rec_id: str) -> bool:
    rec = session.get(Recording, rec_id)
    if rec is None:
        return False
    session.delete(rec)
    session.commit()
    return True


def update_recording(session: Session, rec_id: str, *, title: Optional[str] = None,
                     meta: Optional[dict] = None) -> Recording:
    rec = session.get(Recording, rec_id)
    if rec is None:
        raise ValueError(f"recording not found: {rec_id}")
    if title is not None:
        rec.title = title
    if meta is not None:
        rec.meta = meta
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec
