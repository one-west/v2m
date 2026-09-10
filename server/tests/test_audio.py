import io
import shutil
import subprocess

import pytest

from app.core.paths import get_audio_dir

WEBM_BYTES = b"pretend-opus-bytes"


def _upload(client, payload=WEBM_BYTES):
    files = {"file": ("m.webm", io.BytesIO(payload), "audio/webm")}
    return client.post("/api/recordings", files=files).json()["id"]


def test_webm_is_remuxed_in_place_once(client, monkeypatch):
    """MediaRecorder writes no duration, so the browser reports Infinity and cannot
    seek. A `-c copy` remux restores it losslessly, so the upgraded file *replaces*
    the original rather than doubling a multi-GB archive."""
    import app.api.recordings as rec_mod

    calls = []

    def fake_remux(src, dst, exe):
        calls.append(src)
        dst.write_bytes(b"remuxed-webm")

    monkeypatch.setattr(rec_mod, "remux_webm", fake_remux)
    # A durationless original, and a remux output that probes as valid.
    monkeypatch.setattr(rec_mod, "probe_duration",
                        lambda p, exe: 12.0 if p.read_bytes() == b"remuxed-webm" else None)
    rec_id = _upload(client)
    original = get_audio_dir() / f"{rec_id}.webm"

    first = client.get(f"/api/recordings/{rec_id}/audio")
    assert first.status_code == 200
    assert first.content == b"remuxed-webm"
    assert first.headers["content-type"].startswith("audio/webm")
    # Upgraded in place: one file, and it is the remuxed one.
    assert original.read_bytes() == b"remuxed-webm"
    assert list(get_audio_dir().glob(f"{rec_id}*")) == [original]

    assert client.get(f"/api/recordings/{rec_id}/audio").content == b"remuxed-webm"
    assert len(calls) == 1, "an already-remuxed file must not be remuxed again"


def test_webm_serves_the_original_when_ffmpeg_is_missing(client, monkeypatch):
    import app.api.recordings as rec_mod

    monkeypatch.setattr(rec_mod, "find_ffmpeg", lambda _dir: None)
    rec_id = _upload(client)
    resp = client.get(f"/api/recordings/{rec_id}/audio")
    # Playback must keep working without ffmpeg — only seeking degrades.
    assert resp.status_code == 200
    assert resp.content == WEBM_BYTES
    assert (get_audio_dir() / f"{rec_id}.webm").read_bytes() == WEBM_BYTES


def test_a_failed_remux_never_touches_the_original(client, monkeypatch):
    """The recording is irreplaceable: a broken ffmpeg run must leave it untouched."""
    import app.api.recordings as rec_mod

    def broken_remux(src, dst, exe):
        dst.write_bytes(b"half")  # ffmpeg died mid-write
        raise RuntimeError("ffmpeg exited 1")

    monkeypatch.setattr(rec_mod, "remux_webm", broken_remux)
    rec_id = _upload(client)
    resp = client.get(f"/api/recordings/{rec_id}/audio")

    assert resp.status_code == 200
    assert resp.content == WEBM_BYTES
    original = get_audio_dir() / f"{rec_id}.webm"
    assert original.read_bytes() == WEBM_BYTES
    assert list(get_audio_dir().glob(f"{rec_id}*")) == [original], "no temp file left behind"


def test_a_remux_producing_an_unreadable_file_never_touches_the_original(client, monkeypatch):
    """ffmpeg can exit 0 and still write something unusable — verify before replacing."""
    import app.api.recordings as rec_mod

    monkeypatch.setattr(rec_mod, "remux_webm", lambda src, dst, exe: dst.write_bytes(b""))
    rec_id = _upload(client)
    resp = client.get(f"/api/recordings/{rec_id}/audio")

    assert resp.status_code == 200
    assert resp.content == WEBM_BYTES
    assert (get_audio_dir() / f"{rec_id}.webm").read_bytes() == WEBM_BYTES


def test_audio_responses_must_be_revalidated(client, monkeypatch):
    """Without Cache-Control a browser applies heuristic freshness and will keep
    serving a stale body after the file behind the URL changes (e.g. the remux
    appearing once ffmpeg is installed). ETag keeps revalidation cheap."""
    import app.api.recordings as rec_mod

    monkeypatch.setattr(rec_mod, "remux_webm", lambda src, dst, exe: dst.write_bytes(b"remuxed"))
    monkeypatch.setattr(rec_mod, "transcode_to_mp3", lambda src, dst, exe: dst.write_bytes(b"mp3"))
    rec_id = _upload(client)
    for fmt in ("webm", "mp3"):
        resp = client.get(f"/api/recordings/{rec_id}/audio", params={"format": fmt})
        assert resp.headers.get("cache-control") == "no-cache", fmt


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
    assert (get_audio_dir() / f"{rec_id}.mp3").exists()

    client.delete(f"/api/recordings/{rec_id}")
    assert list(get_audio_dir().glob(f"{rec_id}*")) == []


def _durationless_webm(tmp_path):
    """A webm with no duration in its header, the way MediaRecorder writes them."""
    full = tmp_path / "tone.webm"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=1", "-c:a", "libopus", str(full)],
        check=True,
    )
    stripped = tmp_path / "live.webm"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(full),
         "-c", "copy", "-live", "1", str(stripped)],
        check=True,
    )
    return stripped


def _probe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-hide_banner", "-loglevel", "error", "-show_entries",
         "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return None if out in ("", "N/A") else float(out)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")
def test_real_ffmpeg_restores_the_duration_a_browser_needs_to_seek(client, tmp_path):
    src = _durationless_webm(tmp_path)
    assert _probe_duration(src) is None, "fixture must start with no duration"
    rec_id = _upload(client, src.read_bytes())

    resp = client.get(f"/api/recordings/{rec_id}/audio")
    assert resp.status_code == 200
    served = tmp_path / "served.webm"
    served.write_bytes(resp.content)
    assert _probe_duration(served) == pytest.approx(1.0, abs=0.2)
    # The stored recording itself is upgraded, so it stays seekable forever.
    assert _probe_duration(get_audio_dir() / f"{rec_id}.webm") == pytest.approx(1.0, abs=0.2)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")
def test_real_ffmpeg_produces_a_playable_mp3(client, tmp_path):
    """End-to-end through the actual encoder — the mocked tests above only cover caching."""
    rec_id = _upload(client, _durationless_webm(tmp_path).read_bytes())

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
