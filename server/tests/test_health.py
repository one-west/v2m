def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert body["models_ready"] is False  # no HF token in test env


def test_models_ready_without_token_when_diarization_is_off(engine, transcriber, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.core.config import get_settings
    from app.main import create_app

    monkeypatch.setenv("V2M_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("V2M_HF_TOKEN", "")
    # Fast mode needs no HuggingFace token: nothing gated is downloaded.
    monkeypatch.setenv("V2M_DIARIZE", "false")
    get_settings.cache_clear()
    app = create_app(engine=engine, transcriber=transcriber, shutdown_hook=lambda: None)
    body = TestClient(app).get("/health").json()
    assert body["models_ready"] is True
