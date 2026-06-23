import os
import signal
import threading
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.api.recordings import router as recordings_router
from app.core.config import get_settings
from app.core.health import check_models_ready
from app.store import db as db_module

VERSION = "0.1.0"


def _default_transcriber(settings):
    from app.transcribe.whisperx_runner import WhisperXTranscriber
    return WhisperXTranscriber(model_size=settings.whisper_model, hf_token=settings.hf_token)


def _default_shutdown() -> None:
    def _send_sigterm():
        import time
        time.sleep(1)
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Thread(target=_send_sigterm, daemon=True).start()


def create_app(*, engine=None, transcriber=None, shutdown_hook=None) -> FastAPI:
    settings = get_settings()
    if engine is None:
        engine = db_module.get_engine()
        db_module.init_db(engine)
    if transcriber is None:
        transcriber = _default_transcriber(settings)

    app = FastAPI(title="V2M", version=VERSION)
    app.state.engine = engine
    app.state.transcriber = transcriber
    app.state.settings = settings
    app.state.shutdown_hook = shutdown_hook or _default_shutdown

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "version": VERSION, "models_ready": check_models_ready(settings)}

    @app.post("/shutdown")
    def shutdown(request: Request) -> dict:
        request.app.state.shutdown_hook()
        return {"status": "shutting_down"}

    app.include_router(recordings_router)

    dist = Path(__file__).resolve().parent.parent.parent / "web" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="static")

    return app
