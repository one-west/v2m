import io

from app.prompt.builder import build_prompt, format_transcript

SAMPLE = {
    "segments": [
        {"speaker": "SPEAKER_00", "start_ms": 0, "end_ms": 3000, "text": "회의를 시작합니다."},
        {"speaker": "SPEAKER_00", "start_ms": 3000, "end_ms": 5000, "text": "안건은 두 가지입니다."},
        {"speaker": "SPEAKER_01", "start_ms": 65000, "end_ms": 67000, "text": "네 동의합니다."},
    ],
    "full_text": "회의를 시작합니다. 안건은 두 가지입니다. 네 동의합니다.",
    "language": "ko",
}


def test_format_groups_consecutive_speaker_and_timestamps():
    text = format_transcript(SAMPLE)
    assert "[00:00] SPEAKER_00:" in text
    assert "[01:05] SPEAKER_01:" in text
    # consecutive SPEAKER_00 lines merged under one header
    assert text.count("SPEAKER_00:") == 1


def test_build_prompt_includes_instruction_and_transcript():
    bundle = build_prompt(SAMPLE)
    assert "회의록" in bundle.prompt
    assert "SPEAKER_00" in bundle.prompt
    assert bundle.char_count == len(bundle.prompt)
    assert bundle.too_long is False


def test_too_long_flag():
    big = {"segments": [{"speaker": "S", "start_ms": 0, "end_ms": 1, "text": "가" * 50000}],
           "full_text": "x", "language": "ko"}
    assert build_prompt(big).too_long is True


def test_prompt_endpoint_200_when_ready(client):
    # upload but force status away from done by deleting transcript
    files = {"file": ("m.webm", io.BytesIO(b"a"), "audio/webm")}
    rec_id = client.post("/api/recordings", files=files).json()["id"]
    # FakeTranscriber already produced a transcript → endpoint should be 200
    resp = client.get(f"/api/recordings/{rec_id}/prompt")
    assert resp.status_code == 200
    assert "transcript_text" in resp.json()


def test_prompt_endpoint_409_when_not_ready(client, engine):
    from sqlmodel import Session
    from app.store import repo
    with Session(engine) as s:
        rec = repo.create_recording(s, title="X", audio_path="/x.webm")
        rec_id = rec.id
    resp = client.get(f"/api/recordings/{rec_id}/prompt")
    assert resp.status_code == 409
