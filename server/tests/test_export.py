import io

from app.export.markdown import content_disposition, to_markdown, to_txt


def test_content_disposition_uses_title():
    cd = content_disposition("weekly-sync", "md", "abc123")
    assert 'filename="weekly-sync.md"' in cd
    assert "filename*=UTF-8''weekly-sync.md" in cd


def test_content_disposition_korean_title_keeps_utf8_and_ascii_fallback():
    cd = content_disposition("주간 회의", "txt", "abc123")
    assert 'filename="abc123.txt"' in cd  # ASCII fallback = id
    assert "filename*=UTF-8''" in cd
    assert "주간" not in cd  # the UTF-8 part is percent-encoded, not raw


def test_content_disposition_blank_title_falls_back_to_id():
    cd = content_disposition("   ", "md", "abc123")
    assert 'filename="abc123.md"' in cd


def test_export_endpoint_filename_uses_title(client):
    files = {"file": ("m.webm", io.BytesIO(b"a"), "audio/webm")}
    rec_id = client.post("/api/recordings", files=files, data={"title": "weekly-sync"}).json()["id"]
    resp = client.get(f"/api/recordings/{rec_id}/export?format=md")
    assert resp.status_code == 200
    assert "weekly-sync.md" in resp.headers["content-disposition"]
    assert rec_id not in resp.headers["content-disposition"].split("filename=")[1]

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


def test_export_includes_meta_block():
    md = to_markdown("회의", SAMPLE, {"location": "A"})
    assert "회의 정보" in md and "A" in md
    txt = to_txt("회의", SAMPLE, {"location": "A"})
    assert "회의 정보" in txt


def test_export_without_meta_has_no_block():
    assert "회의 정보" not in to_markdown("회의", SAMPLE)
    assert "회의 정보" not in to_txt("회의", SAMPLE)
