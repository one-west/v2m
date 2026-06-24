import sys
import types

from app.transcribe.whisperx_runner import WhisperXTranscriber


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
