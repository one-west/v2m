import io
import json


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


def _post_with_meta(client, *, title="회의", meta=None):
    files = {"file": ("recording.webm", io.BytesIO(b"audio-bytes"), "audio/webm")}
    data = {"title": title}
    if meta is not None:
        data["meta"] = json.dumps(meta, ensure_ascii=False)
    return client.post("/api/recordings", files=files, data=data)


def test_post_stores_and_returns_meta(client):
    meta = {"location": "회의실 A", "attendees": "홍길동", "agenda": "킥오프"}
    r = _post_with_meta(client, meta=meta)
    assert r.status_code == 201
    rec_id = r.json()["id"]
    assert r.json()["meta"] == meta
    got = client.get(f"/api/recordings/{rec_id}").json()
    assert got["meta"]["location"] == "회의실 A"


def test_post_without_meta_is_null(client):
    r = _post_with_meta(client)
    assert r.status_code == 201
    assert r.json()["meta"] is None


def test_list_includes_meta(client):
    _post_with_meta(client, meta={"agenda": "X"})
    rows = client.get("/api/recordings").json()
    assert rows[0]["meta"] == {"agenda": "X"}


def test_patch_updates_meta_and_title(client):
    rec_id = _post_with_meta(client, title="원본").json()["id"]
    r = client.patch(f"/api/recordings/{rec_id}",
                      json={"title": "수정본", "meta": {"location": "B룸"}})
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "수정본"
    assert body["meta"]["location"] == "B룸"
    assert "transcript" in body  # full detail shape


def test_patch_unknown_id_404(client):
    r = client.patch("/api/recordings/missing", json={"title": "x"})
    assert r.status_code == 404
