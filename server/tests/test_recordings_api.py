import io


def _upload(client, name="m.webm"):
    files = {"file": (name, io.BytesIO(b"a"), "audio/webm")}
    return client.post("/api/recordings", files=files).json()["id"]


def test_list_returns_uploaded(client):
    _upload(client)
    rows = client.get("/api/recordings").json()
    assert len(rows) == 1
    assert {"id", "title", "status", "created_at"} <= set(rows[0])


def test_detail_404(client):
    assert client.get("/api/recordings/nope").status_code == 404


def test_delete_removes_record(client):
    rec_id = _upload(client)
    assert client.delete(f"/api/recordings/{rec_id}").status_code == 204
    assert client.get(f"/api/recordings/{rec_id}").status_code == 404


def test_retry_reschedules(client):
    rec_id = _upload(client)
    resp = client.post(f"/api/recordings/{rec_id}/retry")
    assert resp.status_code == 200
    # With FakeTranscriber, retry ends in done again
    assert client.get(f"/api/recordings/{rec_id}/status").json()["status"] == "done"
