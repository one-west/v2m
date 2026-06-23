import io


def test_upload_creates_recording_and_runs_job(client):
    files = {"file": ("meeting.webm", io.BytesIO(b"fakeaudio"), "audio/webm")}
    resp = client.post("/api/recordings", files=files, data={"title": "Sprint Review"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Sprint Review"
    rec_id = body["id"]

    # BackgroundTasks run after the response with the FakeTranscriber → done
    status = client.get(f"/api/recordings/{rec_id}/status").json()
    assert status["status"] == "done"

    detail = client.get(f"/api/recordings/{rec_id}").json()
    assert detail["transcript"]["language"] == "ko"


def test_upload_defaults_title_when_missing(client):
    files = {"file": ("m.webm", io.BytesIO(b"a"), "audio/webm")}
    resp = client.post("/api/recordings", files=files)
    assert resp.status_code == 201
    assert resp.json()["title"]


def test_upload_write_failure_leaves_no_orphan_row(client, monkeypatch, tmp_path):
    import app.api.recordings as rec_mod
    # Point audio dir at a path whose parent does not exist so write_bytes fails
    monkeypatch.setattr(rec_mod, "get_audio_dir", lambda: tmp_path / "missing_parent" / "sub")
    files = {"file": ("m.webm", io.BytesIO(b"a"), "audio/webm")}
    resp = client.post("/api/recordings", files=files)
    assert resp.status_code == 500
    assert client.get("/api/recordings").json() == []
