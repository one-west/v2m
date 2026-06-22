import io

from app.export.markdown import to_markdown, to_txt

SAMPLE = {
    "segments": [{"speaker": "SPEAKER_00", "start_ms": 0, "end_ms": 1000, "text": "안녕하세요"}],
    "full_text": "안녕하세요", "language": "ko",
}


def test_to_markdown_has_title_and_text():
    md = to_markdown("주간회의", SAMPLE)
    assert md.startswith("# 주간회의")
    assert "SPEAKER_00" in md
    assert "안녕하세요" in md


def test_to_txt_plain():
    txt = to_txt("주간회의", SAMPLE)
    assert "주간회의" in txt
    assert "안녕하세요" in txt


def test_export_endpoint_md(client):
    files = {"file": ("m.webm", io.BytesIO(b"a"), "audio/webm")}
    rec_id = client.post("/api/recordings", files=files).json()["id"]
    resp = client.get(f"/api/recordings/{rec_id}/export?format=md")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert "attachment" in resp.headers.get("content-disposition", "")


def test_export_bad_format(client):
    files = {"file": ("m.webm", io.BytesIO(b"a"), "audio/webm")}
    rec_id = client.post("/api/recordings", files=files).json()["id"]
    assert client.get(f"/api/recordings/{rec_id}/export?format=pdf").status_code == 400


def test_export_409_when_not_ready(client, engine):
    from sqlmodel import Session
    from app.store import repo
    with Session(engine) as s:
        rec_id = repo.create_recording(s, title="X", audio_path="/x.webm").id
    assert client.get(f"/api/recordings/{rec_id}/export?format=md").status_code == 409


def test_export_404_missing(client):
    assert client.get("/api/recordings/nope/export?format=md").status_code == 404
