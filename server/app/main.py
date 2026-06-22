from fastapi import FastAPI

from app.core.config import get_settings
from app.core.health import check_models_ready
from app.store import db as db_module

VERSION = "0.1.0"


def create_app(*, engine=None, transcriber=None) -> FastAPI:
    settings = get_settings()
    if engine is None:
        engine = db_module.get_engine()
        db_module.init_db(engine)

    app = FastAPI(title="V2M", version=VERSION)
    app.state.engine = engine
    app.state.transcriber = transcriber
    app.state.settings = settings

    @app.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "version": VERSION,
            "models_ready": check_models_ready(settings),
        }

    return app
