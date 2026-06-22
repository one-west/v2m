import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app
from app.store import db
from app.transcribe.fake import FakeTranscriber


@pytest.fixture
def engine(tmp_path):
    e = db.get_engine(tmp_path / "test.db")
    db.init_db(e)
    return e


@pytest.fixture
def transcriber():
    return FakeTranscriber()


@pytest.fixture
def client(engine, transcriber, tmp_path, monkeypatch):
    monkeypatch.setenv("V2M_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("V2M_HF_TOKEN", raising=False)
    get_settings.cache_clear()
    app = create_app(engine=engine, transcriber=transcriber)
    return TestClient(app)
