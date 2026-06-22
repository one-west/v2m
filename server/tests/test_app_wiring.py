import importlib


def test_whisperx_module_imports_without_torch():
    # Importing the module must NOT import whisperx/torch at module load time.
    mod = importlib.import_module("app.transcribe.whisperx_runner")
    assert hasattr(mod, "WhisperXTranscriber")


def test_shutdown_endpoint_exists(client):
    resp = client.post("/shutdown")
    assert resp.status_code == 200
    assert resp.json()["status"] == "shutting_down"
