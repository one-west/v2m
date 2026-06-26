import importlib


def test_whisperx_module_imports_without_torch():
    # Importing the module must NOT import whisperx/torch at module load time.
    mod = importlib.import_module("app.transcribe.whisperx_runner")
    assert hasattr(mod, "WhisperXTranscriber")


def test_whisperx_transcriber_stores_perf_params_without_torch():
    # Constructing the real transcriber must stay torch-free and carry the perf knobs.
    from app.transcribe.whisperx_runner import WhisperXTranscriber

    t = WhisperXTranscriber(model_size="small", hf_token="", batch_size=8, cpu_threads=4,
                            language="en")
    assert t.batch_size == 8
    assert t.cpu_threads == 4
    assert t.language == "en"
    # Defaults: batched + auto threads + Korean + numeral suppression on, no prompt.
    d = WhisperXTranscriber(model_size="small", hf_token="")
    assert d.batch_size == 16
    assert d.cpu_threads == 0
    assert d.language == "ko"
    assert d.suppress_numerals is True
    assert d.initial_prompt == ""
    assert d.vad_method == "silero"
    assert d.diarize is True


def test_shutdown_endpoint_exists(client):
    resp = client.post("/shutdown")
    assert resp.status_code == 200
    assert resp.json()["status"] == "shutting_down"


def test_shutdown_invokes_hook(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.store import db
    from app.transcribe.fake import FakeTranscriber
    e = db.get_engine(tmp_path / "t.db")
    db.init_db(e)
    called = []
    app = create_app(engine=e, transcriber=FakeTranscriber(), shutdown_hook=lambda: called.append(True))
    client = TestClient(app)
    resp = client.post("/shutdown")
    assert resp.status_code == 200
    assert resp.json()["status"] == "shutting_down"
    assert called == [True]
