import io
import shutil
import subprocess

import pytest

from app.core.paths import get_audio_dir

WEBM_BYTES = b"pretend-opus-bytes"


def _upload(client, payload=WEBM_BYTES):
    files = {"file": ("m.webm", io.BytesIO(payload), "audio/webm")}
    return client.post("/api/recordings", files=files).json()["id"]


def test_serves_the_original_webm(client):
    rec_id = _upload(client)
    resp = client.get(f"/api/recordings/{rec_id}/audio")
    assert resp.status_code == 200
    assert resp.content == WEBM_BYTES
    assert resp.headers["content-type"].startswith("audio/webm")


def test_audio_404_for_unknown_recording(client):
    assert client.get("/api/recordings/nope/audio").status_code == 404


def test_rejects_unknown_format(client):
    rec_id = _upload(client)
    assert client.get(f"/api/recordings/{rec_id}/audio", params={"format": "flac"}).status_code == 400


def test_mp3_transcodes_once_then_serves_the_cached_file(client, monkeypatch):
    import app.api.recordings as rec_mod

    calls = []

    def fake_transcode(src, dst, exe):
        calls.append(src)
        dst.write_bytes(b"ID3-mp3-bytes")

    monkeypatch.setattr(rec_mod, "transcode_to_mp3", fake_transcode)
    rec_id = _upload(client)

    first = client.get(f"/api/recordings/{rec_id}/audio", params={"format": "mp3"})
    assert first.status_code == 200
    assert first.content == b"ID3-mp3-bytes"
    assert first.headers["content-type"].startswith("audio/mpeg")

    second = client.get(f"/api/recordings/{rec_id}/audio", params={"format": "mp3"})
    assert second.content == b"ID3-mp3-bytes"
    # Converting a multi-hour recording is slow; the second request must reuse the file.
    assert len(calls) == 1


def test_mp3_returns_503_when_ffmpeg_is_unavailable(client, monkeypatch):
    import app.api.recordings as rec_mod

    monkeypatch.setattr(rec_mod, "find_ffmpeg", lambda _dir: None)
    rec_id = _upload(client)
    resp = client.get(f"/api/recordings/{rec_id}/audio", params={"format": "mp3"})
    assert resp.status_code == 503
    assert "ffmpeg" in resp.json()["detail"].lower()


def test_failed_transcode_leaves_no_partial_cache(client, monkeypatch):
    import app.api.recordings as rec_mod

    def broken_transcode(src, dst, exe):
        dst.write_bytes(b"half")  # ffmpeg died mid-write
        raise RuntimeError("ffmpeg exited 1")

    monkeypatch.setattr(rec_mod, "transcode_to_mp3", broken_transcode)
    rec_id = _upload(client)

    assert client.get(f"/api/recordings/{rec_id}/audio", params={"format": "mp3"}).status_code == 500
    # A truncated file must not be served as a valid cache on the next request.
    assert not (get_audio_dir() / f"{rec_id}.mp3").exists()


def test_delete_removes_the_mp3_cache_too(client, monkeypatch):
    import app.api.recordings as rec_mod

    monkeypatch.setattr(rec_mod, "transcode_to_mp3",
                        lambda src, dst, exe: dst.write_bytes(b"ID3-mp3-bytes"))
    rec_id = _upload(client)
    client.get(f"/api/recordings/{rec_id}/audio", params={"format": "mp3"})
    mp3 = get_audio_dir() / f"{rec_id}.mp3"
    assert mp3.exists()

    client.delete(f"/api/recordings/{rec_id}")
    assert not mp3.exists()
    assert not (get_audio_dir() / f"{rec_id}.webm").exists()


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")
def test_real_ffmpeg_produces_a_playable_mp3(client, tmp_path):
    """End-to-end through the actual encoder — the mocked tests above only cover caching."""
    src = tmp_path / "tone.webm"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=1", "-c:a", "libopus", str(src)],
        check=True,
    )
    rec_id = _upload(client, src.read_bytes())

    resp = client.get(f"/api/recordings/{rec_id}/audio", params={"format": "mp3"})
    assert resp.status_code == 200
    assert resp.content[:3] == b"ID3" or resp.content[:2] == b"\xff\xfb"

    out = tmp_path / "out.mp3"
    out.write_bytes(resp.content)
    probe = subprocess.run(
        ["ffprobe", "-hide_banner", "-loglevel", "error", "-show_entries",
         "stream=codec_name", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, check=True,
    )
    assert "mp3" in probe.stdout
