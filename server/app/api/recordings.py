from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, Response, UploadFile
from sqlmodel import Session

from app.jobs.queue import run_transcription
from app.core.paths import get_audio_dir
from app.store import repo
from app.store.models import RecordingStatus

router = APIRouter(prefix="/api")


def _schedule(request: Request, background: BackgroundTasks, rec_id: str) -> None:
    background.add_task(
        run_transcription,
        rec_id,
        transcriber=request.app.state.transcriber,
        engine=request.app.state.engine,
    )


@router.post("/recordings", status_code=201)
async def create_recording(
    request: Request,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(default=""),
):
    engine = request.app.state.engine
    with Session(engine) as session:
        rec = repo.create_recording(
            session,
            title=title or f"녹음 {datetime.now():%Y-%m-%d %H:%M}",
            audio_path="",
        )
        rec_id = rec.id

    dest = get_audio_dir() / f"{rec_id}.webm"
    try:
        dest.write_bytes(await file.read())
    except Exception:
        with Session(engine) as session:
            repo.delete_recording(session, rec_id)
        raise HTTPException(status_code=500, detail="failed to save audio")

    with Session(engine) as session:
        rec = repo.get_recording(session, rec_id)
        rec.audio_path = str(dest)
        session.add(rec)
        session.commit()
        session.refresh(rec)
        payload = {"id": rec.id, "title": rec.title, "status": rec.status,
                   "created_at": rec.created_at.isoformat()}

    _schedule(request, background, rec_id)
    return payload


@router.get("/recordings")
def list_recordings(request: Request):
    with Session(request.app.state.engine) as session:
        return [
            {"id": r.id, "title": r.title, "status": r.status,
             "created_at": r.created_at.isoformat(), "duration_sec": r.duration_sec}
            for r in repo.list_recordings(session)
        ]


def _get_or_404(session: Session, rec_id: str):
    rec = repo.get_recording(session, rec_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="recording not found")
    return rec


@router.get("/recordings/{rec_id}")
def get_recording(request: Request, rec_id: str):
    with Session(request.app.state.engine) as session:
        rec = _get_or_404(session, rec_id)
        return {"id": rec.id, "title": rec.title, "status": rec.status,
                "created_at": rec.created_at.isoformat(), "duration_sec": rec.duration_sec,
                "error": rec.error, "transcript": rec.transcript}


@router.get("/recordings/{rec_id}/status")
def get_status(request: Request, rec_id: str):
    with Session(request.app.state.engine) as session:
        rec = _get_or_404(session, rec_id)
        return {"id": rec.id, "status": rec.status, "error": rec.error}


@router.post("/recordings/{rec_id}/retry")
def retry(request: Request, background: BackgroundTasks, rec_id: str):
    with Session(request.app.state.engine) as session:
        rec = _get_or_404(session, rec_id)
        repo.update_status(session, rec_id, RecordingStatus.RECORDED)
    _schedule(request, background, rec_id)
    return {"id": rec_id, "status": "scheduled"}


@router.delete("/recordings/{rec_id}", status_code=204)
def delete_recording(request: Request, rec_id: str):
    with Session(request.app.state.engine) as session:
        rec = _get_or_404(session, rec_id)
        audio = Path(rec.audio_path) if rec.audio_path else None
        repo.delete_recording(session, rec_id)
    if audio and audio.exists():
        audio.unlink()
    return Response(status_code=204)
