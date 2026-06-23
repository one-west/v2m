from pathlib import Path

from app.transcribe.base import TranscriptResult, TranscriptSegment
from app.transcribe.fake import FakeTranscriber


def test_fake_returns_default_result():
    t = FakeTranscriber()
    result = t.transcribe(Path("/tmp/a.webm"))
    assert isinstance(result, TranscriptResult)
    assert len(result.segments) >= 1
    assert result.language == "ko"
    assert t.last_audio_path == Path("/tmp/a.webm")


def test_fake_returns_injected_result():
    custom = TranscriptResult(
        segments=[TranscriptSegment(speaker="SPEAKER_00", start_ms=0, end_ms=1000, text="안녕")],
        full_text="안녕",
        language="ko",
    )
    t = FakeTranscriber(result=custom)
    assert t.transcribe(Path("/x")).full_text == "안녕"


def test_to_dict_roundtrip():
    custom = TranscriptResult(
        segments=[TranscriptSegment(speaker="SPEAKER_00", start_ms=0, end_ms=1000, text="hi")],
        full_text="hi", language="ko",
    )
    d = custom.to_dict()
    assert d["full_text"] == "hi"
    assert d["segments"][0]["speaker"] == "SPEAKER_00"
