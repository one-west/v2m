import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session

from app.jobs.queue import run_transcription
from app.core.ffmpeg import find_ffmpeg, probe_duration, remux_webm, transcode_to_mp3
from app.core.paths import get_audio_dir
from app.export.markdown import content_disposition, to_markdown, to_txt
from app.prompt.builder import build_prompt
from app.store import repo
from app.store.models import RecordingStatus

router = APIRouter(prefix="/api")


class RecordingPatch(BaseModel):
    title: str | None = None
    meta: dict | None = None


def _detail(rec) -> dict:
    """The full single-recording shape. One definition so every endpoint that
    returns a recording stays in sync (GET and PATCH used to drift)."""
    return {"id": rec.id, "title": rec.title, "status": rec.status,
            "created_at": rec.created_at.isoformat(), "error": rec.error, "transcript": rec.transcript, "meta": rec.meta,
            "language": rec.language, "stage": rec.stage}


def _derived(source: Path, suffix: str) -> Path:
    return source.parent / f"{source.stem}{suffix}"


def _ensure_seekable(source: Path, exe: str) -> None:
    """Upgrade a MediaRecorder WebM in place so browsers can seek it.

    MediaRecorder streams its output live and never writes a duration into the
    container, so `<audio>` reports `duration === Infinity` and the scrubber does
    nothing. A `-c copy` remux restores it — lossless and fast (~0.3s for 68 MB of
    audio, ~1s for 194 MB), which is why the result replaces the original instead
    of being cached alongside it: these archives run to gigabytes.

    The recording is irreplaceable, so the original is only unlinked once ffmpeg
    has succeeded AND the result probes as a readable file with a duration. Any
    failure leaves the original exactly as it was; playback still works, without
    seeking. Best-effort throughout — never raises.
    """
    try:
        if probe_duration(source, exe) is not None:
            return  # already seekable (remuxed before, or not from MediaRecorder)
        tmp = source.with_name(f"{source.stem}.remux.tmp{source.suffix}")
        try:
            remux_webm(source, tmp, exe)
            if probe_duration(tmp, exe) is None:
                raise RuntimeError("remux produced a file with no readable duration")
            os.replace(tmp, source)  # atomic on the same volume
        finally:
            tmp.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001 - seeking is a bonus; playback must not break
        pass


def _audio_headers(title: str, ext: str, rec_id: str) -> dict:
    # no-cache = revalidate, not "don't store": the file behind a URL can change
    # (the remux appears once ffmpeg is available), and without an explicit
    # Cache-Control browsers apply heuristic freshness and serve the stale body
    # for hours. FileResponse still sends an ETag, so revalidation is a cheap 304.
    return {"Content-Disposition": content_disposition(title, ext, rec_id),
            "Cache-Control": "no-cache"}


def _schedule(request: Request, background: BackgroundTasks, rec_id: str) -> None:
    background.add_task(
        run_transcription,
        rec_id,
        transcriber=request.app.state.transcriber,
        engine=request.app.state.engine,
    )


# Sync (not async) on purpose: FastAPI runs it in a threadpool, so the blocking
# file copy below never stalls the event loop.
@router.post("/recordings", status_code=201)
def create_recording(
    request: Request,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(default=""),
    meta: str = Form(default=""),
    language: str = Form(default=""),
):
    try:
        parsed_meta = json.loads(meta) if meta else None
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="meta must be valid JSON")
    engine = request.app.state.engine
    with Session(engine) as session:
        rec = repo.create_recording(
            session,
            title=title or f"녹음 {datetime.now():%Y-%m-%d %H:%M}",
            audio_path="",
            language=language or None,
        )
        rec_id = rec.id
        if parsed_meta is not None:
            repo.update_recording(session, rec_id, meta=parsed_meta)

    dest = get_audio_dir() / f"{rec_id}.webm"
    try:
        # Stream the upload to disk. A multi-hour meeting is hundreds of MB, and
        # reading it whole would spike RSS by that much for the length of the request.
        with dest.open("wb") as out:
            shutil.copyfileobj(file.file, out)
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
                   "created_at": rec.created_at.isoformat(), "meta": rec.meta,
                   "language": rec.language}

    _schedule(request, background, rec_id)
    return payload


@router.get("/recordings")
def list_recordings(request: Request):
    with Session(request.app.state.engine) as session:
        return [
            {"id": r.id, "title": r.title, "status": r.status,
             "created_at": r.created_at.isoformat(), "meta": r.meta, "language": r.language, "stage": r.stage}
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
        return _detail(_get_or_404(session, rec_id))


@router.patch("/recordings/{rec_id}")
def patch_recording(request: Request, rec_id: str, body: RecordingPatch):
    with Session(request.app.state.engine) as session:
        _get_or_404(session, rec_id)
        return _detail(repo.update_recording(session, rec_id, title=body.title, meta=body.meta))


@router.get("/recordings/{rec_id}/status")
def get_status(request: Request, rec_id: str):
    with Session(request.app.state.engine) as session:
        rec = _get_or_404(session, rec_id)
        return {"id": rec.id, "status": rec.status, "error": rec.error, "stage": rec.stage}


@router.get("/recordings/{rec_id}/prompt")
def get_prompt(request: Request, rec_id: str):
    with Session(request.app.state.engine) as session:
        rec = _get_or_404(session, rec_id)
        if not rec.transcript:
            raise HTTPException(status_code=409, detail="transcript not ready")
        return build_prompt(rec.transcript, rec.meta).model_dump()


@router.get("/recordings/{rec_id}/export")
def export(request: Request, rec_id: str, format: str = "md"):
    if format not in ("md", "txt"):
        raise HTTPException(status_code=400, detail="format must be md or txt")
    with Session(request.app.state.engine) as session:
        rec = _get_or_404(session, rec_id)
        if not rec.transcript:
            raise HTTPException(status_code=409, detail="transcript not ready")
        if format == "md":
            content, media, ext = to_markdown(rec.title, rec.transcript, rec.meta), "text/markdown", "md"
        else:
            content, media, ext = to_txt(rec.title, rec.transcript, rec.meta), "text/plain", "txt"
    headers = {"Content-Disposition": content_disposition(rec.title, ext, rec_id)}
    return Response(content=content, media_type=media, headers=headers)


# Sync on purpose: an MP3 conversion can take a minute on a long recording, and a
# sync endpoint runs in FastAPI's threadpool instead of blocking the event loop.
@router.get("/recordings/{rec_id}/audio")
def get_audio(request: Request, rec_id: str, format: str = "webm"):
    if format not in ("webm", "mp3"):
        raise HTTPException(status_code=400, detail="format must be webm or mp3")
    with Session(request.app.state.engine) as session:
        rec = _get_or_404(session, rec_id)
        source = Path(rec.audio_path) if rec.audio_path else None
        title = rec.title
    if source is None or not source.is_file():
        raise HTTPException(status_code=404, detail="audio file not found")

    exe = find_ffmpeg(request.app.state.settings.ffmpeg_dir)

    if format == "webm":
        if exe is not None:
            _ensure_seekable(source, exe)
        return FileResponse(source, media_type="audio/webm",
                            headers=_audio_headers(title, "webm", rec_id))

    # Convert once and keep the result next to the original: re-encoding a
    # multi-hour meeting on every download would cost a minute each time.
    mp3 = _derived(source, ".mp3")
    if not mp3.is_file():
        if exe is None:
            raise HTTPException(
                status_code=503,
                detail="mp3 변환에는 ffmpeg가 필요합니다. ffmpeg를 설치하거나 V2M_FFMPEG_DIR를 설정해 주세요.",
            )
        try:
            transcode_to_mp3(source, mp3, exe)
        except Exception as exc:  # noqa: BLE001 - surface any encoder failure as 500
            # Never leave a truncated file behind: it would be served as a valid cache.
            mp3.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail=f"mp3 변환에 실패했습니다: {exc}")
    return FileResponse(mp3, media_type="audio/mpeg", headers=_audio_headers(title, "mp3", rec_id))


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
    if audio:
        # Every file this recording owns is `{uuid}.<something>` in the audio dir:
        # the recording itself, the mp3 download cache, and any remux temp left by a
        # process killed mid-convert. Globbing the id covers all of them — and any
        # derivative added later — without a list to keep in sync. The id is a uuid4
        # hex generated by us, so the pattern cannot reach another recording's files.
        for path in audio.parent.glob(f"{audio.stem}.*"):
            path.unlink(missing_ok=True)
    return Response(status_code=204)
