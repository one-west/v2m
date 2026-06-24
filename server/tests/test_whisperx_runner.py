import sys
import types
from pathlib import Path

from app.transcribe.whisperx_runner import WhisperXTranscriber


def test_transcribe_forces_configured_language_and_maps_segments(monkeypatch, tmp_path):
    monkeypatch.setenv("V2M_DATA_DIR", str(tmp_path))
    captured = {}

    class _FakeModel:
        def transcribe(self, audio, batch_size=None, language=None):
            captured["batch_size"] = batch_size
            captured["language"] = language
            return {"segments": [{"start": 0.0, "end": 1.0, "text": "안녕"}],
                    "language": language or "auto"}

    fake_wx = types.ModuleType("whisperx")
    fake_wx.load_model = lambda *a, **k: _FakeModel()
    fake_wx.load_audio = lambda p: [0.0]
    fake_wx.load_align_model = lambda language_code, device: (f"ALIGN[{language_code}]", "META")
    fake_wx.align = lambda segs, am, meta, audio, device: {"segments": segs}
    fake_wx.assign_word_speakers = lambda diar, aligned: {
        "segments": [{"start": 0.0, "end": 1.0, "text": "안녕", "speaker": "SPEAKER_01"}]
    }
    fake_diarize = types.ModuleType("whisperx.diarize")

    class _FakeDiarize:
        def __init__(self, *a, **k):
            pass

        def __call__(self, audio):
            return "DIAR"

    fake_diarize.DiarizationPipeline = _FakeDiarize
    monkeypatch.setitem(sys.modules, "whisperx", fake_wx)
    monkeypatch.setitem(sys.modules, "whisperx.diarize", fake_diarize)

    t = WhisperXTranscriber(model_size="small", hf_token="", language="ko", batch_size=8)
    result = t.transcribe(Path("dummy.webm"))

    assert captured["language"] == "ko"  # forced, not auto-detected
    assert captured["batch_size"] == 8
    assert result.language == "ko"
    assert [s.text for s in result.segments] == ["안녕"]
    seg = result.segments[0]
    assert seg.speaker == "SPEAKER_01"
    assert seg.start_ms == 0 and seg.end_ms == 1000


def test_transcribe_empty_language_autodetects(monkeypatch, tmp_path):
    monkeypatch.setenv("V2M_DATA_DIR", str(tmp_path))
    captured = {}

    class _FakeModel:
        def transcribe(self, audio, batch_size=None, language=None):
            captured["language"] = language
            return {"segments": [], "language": "ko"}

    fake_wx = types.ModuleType("whisperx")
    fake_wx.load_model = lambda *a, **k: _FakeModel()
    fake_wx.load_audio = lambda p: [0.0]
    fake_wx.load_align_model = lambda language_code, device: ("ALIGN", "META")
    fake_wx.align = lambda segs, am, meta, audio, device: {"segments": segs}
    fake_wx.assign_word_speakers = lambda diar, aligned: {"segments": []}
    fake_diarize = types.ModuleType("whisperx.diarize")
    fake_diarize.DiarizationPipeline = type("D", (), {"__init__": lambda self, *a, **k: None,
                                                      "__call__": lambda self, audio: "DIAR"})
    monkeypatch.setitem(sys.modules, "whisperx", fake_wx)
    monkeypatch.setitem(sys.modules, "whisperx.diarize", fake_diarize)

    t = WhisperXTranscriber(model_size="small", hf_token="", language="")  # empty -> auto
    t.transcribe(Path("dummy.webm"))
    assert captured["language"] is None


def test_models_are_loaded_once_and_cached(monkeypatch, tmp_path):
    """STT model, per-language align model, and diarization pipeline load once."""
    monkeypatch.setenv("V2M_DATA_DIR", str(tmp_path))  # _get_model touches the models dir
    calls = {"model": 0, "align": 0, "diarize": 0}

    fake_wx = types.ModuleType("whisperx")
    fake_wx.load_model = lambda *a, **k: calls.__setitem__("model", calls["model"] + 1) or "MODEL"
    fake_wx.load_align_model = lambda *a, **k: (
        calls.__setitem__("align", calls["align"] + 1) or ("ALIGN", "META")
    )
    fake_diarize = types.ModuleType("whisperx.diarize")

    class _FakeDiarize:
        def __init__(self, *a, **k):
            calls["diarize"] += 1

    fake_diarize.DiarizationPipeline = _FakeDiarize
    monkeypatch.setitem(sys.modules, "whisperx", fake_wx)
    monkeypatch.setitem(sys.modules, "whisperx.diarize", fake_diarize)

    t = WhisperXTranscriber(model_size="small", hf_token="")

    assert t._get_model() == "MODEL"
    assert t._get_model() == "MODEL"  # cached
    assert t._get_align("ko") == ("ALIGN", "META")
    assert t._get_align("ko") == ("ALIGN", "META")  # cached per language
    t._get_diarize()
    t._get_diarize()  # cached

    assert calls == {"model": 1, "align": 1, "diarize": 1}


def test_align_cache_is_per_language(monkeypatch, tmp_path):
    monkeypatch.setenv("V2M_DATA_DIR", str(tmp_path))
    count = {"align": 0}
    fake_wx = types.ModuleType("whisperx")
    fake_wx.load_align_model = lambda *a, **k: count.__setitem__("align", count["align"] + 1) or ("A", "M")
    monkeypatch.setitem(sys.modules, "whisperx", fake_wx)

    t = WhisperXTranscriber(model_size="small", hf_token="")
    t._get_align("ko")
    t._get_align("en")  # different language -> separate load
    t._get_align("ko")  # cached
    assert count["align"] == 2
