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
    stages: list[str] = []
    result = t.transcribe(Path("dummy.webm"), on_stage=stages.append)

    assert stages == ["loading", "transcribing", "aligning", "diarizing"]
    assert captured["language"] == "ko"  # forced, not auto-detected
    # Per-recording override beats the configured default.
    t.transcribe(Path("dummy.webm"), language="en")
    assert captured["language"] == "en"
    # "auto" => let WhisperX detect.
    t.transcribe(Path("dummy.webm"), language="auto")
    assert captured["language"] is None
    assert captured["batch_size"] == 8
    assert result.language == "ko"
    assert [s.text for s in result.segments] == ["안녕"]
    seg = result.segments[0]
    assert seg.speaker == "SPEAKER_01"
    assert seg.start_ms == 0 and seg.end_ms == 1000


def test_fast_mode_skips_align_and_diarize(monkeypatch, tmp_path):
    monkeypatch.setenv("V2M_DATA_DIR", str(tmp_path))
    calls = {"align": 0, "diarize": 0}

    class _FakeModel:
        def transcribe(self, audio, batch_size=None, language=None):
            return {"segments": [{"start": 0.0, "end": 1.0, "text": "안녕"}], "language": "ko"}

    fake_wx = types.ModuleType("whisperx")
    fake_wx.load_model = lambda *a, **k: _FakeModel()
    fake_wx.load_audio = lambda p: [0.0]
    fake_wx.load_align_model = lambda **k: calls.__setitem__("align", calls["align"] + 1) or ("A", "M")
    fake_wx.align = lambda *a, **k: {"segments": []}
    fake_wx.assign_word_speakers = lambda d, a: {"segments": []}
    fake_diarize = types.ModuleType("whisperx.diarize")

    class _Diar:
        def __init__(self, *a, **k):
            calls["diarize"] += 1

        def __call__(self, audio):
            return "D"

    fake_diarize.DiarizationPipeline = _Diar
    monkeypatch.setitem(sys.modules, "whisperx", fake_wx)
    monkeypatch.setitem(sys.modules, "whisperx.diarize", fake_diarize)

    t = WhisperXTranscriber(model_size="small", hf_token="", diarize=False)
    stages: list[str] = []
    res = t.transcribe(Path("x.webm"), on_stage=stages.append)

    assert calls == {"align": 0, "diarize": 0}  # both skipped in fast mode
    assert stages == ["loading", "transcribing"]  # no align/diarize stages reported
    assert [s.text for s in res.segments] == ["안녕"]
    assert res.segments[0].speaker == "SPEAKER_00"  # single-speaker fallback


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


def test_get_model_passes_asr_options(monkeypatch, tmp_path):
    monkeypatch.setenv("V2M_DATA_DIR", str(tmp_path))
    captured: dict = {}
    fake_wx = types.ModuleType("whisperx")
    fake_wx.load_model = lambda *a, **k: captured.update(k) or "MODEL"
    monkeypatch.setitem(sys.modules, "whisperx", fake_wx)

    t = WhisperXTranscriber(model_size="small", hf_token="",
                            suppress_numerals=True, initial_prompt="V2M 회의")
    t._get_model()
    assert captured["asr_options"]["suppress_numerals"] is True
    assert captured["asr_options"]["initial_prompt"] == "V2M 회의"
    assert captured["vad_method"] == "silero"  # fast VAD by default


def test_get_model_omits_empty_initial_prompt(monkeypatch, tmp_path):
    monkeypatch.setenv("V2M_DATA_DIR", str(tmp_path))
    captured: dict = {}
    fake_wx = types.ModuleType("whisperx")
    fake_wx.load_model = lambda *a, **k: captured.update(k) or "MODEL"
    monkeypatch.setitem(sys.modules, "whisperx", fake_wx)

    t = WhisperXTranscriber(model_size="small", hf_token="",
                            suppress_numerals=False, initial_prompt="")
    t._get_model()
    assert captured["asr_options"] == {"suppress_numerals": False}


def test_transcribe_is_serialized(monkeypatch, tmp_path):
    """Concurrent transcriptions must not overlap on the shared whisperx pipeline
    (overlap raced into 'NoneType' object has no attribute 'sot_sequence')."""
    import threading
    import time

    monkeypatch.setenv("V2M_DATA_DIR", str(tmp_path))
    state = {"active": 0, "peak": 0}
    guard = threading.Lock()

    class _FakeModel:
        def transcribe(self, audio, batch_size=None, language=None):
            with guard:
                state["active"] += 1
                state["peak"] = max(state["peak"], state["active"])
            time.sleep(0.05)
            with guard:
                state["active"] -= 1
            return {"segments": [], "language": "ko"}

    fake_wx = types.ModuleType("whisperx")
    fake_wx.load_model = lambda *a, **k: _FakeModel()
    fake_wx.load_audio = lambda p: [0.0]
    fake_wx.load_align_model = lambda language_code, device: ("A", "M")
    fake_wx.align = lambda *a, **k: {"segments": []}
    fake_wx.assign_word_speakers = lambda d, a: {"segments": []}
    fake_diarize = types.ModuleType("whisperx.diarize")
    fake_diarize.DiarizationPipeline = type(
        "D", (), {"__init__": lambda self, *a, **k: None, "__call__": lambda self, a: "D"}
    )
    monkeypatch.setitem(sys.modules, "whisperx", fake_wx)
    monkeypatch.setitem(sys.modules, "whisperx.diarize", fake_diarize)

    t = WhisperXTranscriber(model_size="small", hf_token="")
    threads = [threading.Thread(target=lambda: t.transcribe(Path("x.webm"))) for _ in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    assert state["peak"] == 1  # serialized — never two at once


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


def test_fast_mode_chunks_long_audio_and_offsets_timestamps(monkeypatch, tmp_path):
    monkeypatch.setenv("V2M_DATA_DIR", str(tmp_path))
    import numpy as np
    SR = 16000
    calls = []

    class _FakeModel:
        def transcribe(self, audio, batch_size=None, language=None):
            calls.append(len(audio))
            # one segment per chunk, timed locally at 0..1s within the chunk
            return {"segments": [{"start": 0.0, "end": 1.0, "text": f"seg{len(calls)}"}],
                    "language": "ko"}

    fake_wx = types.ModuleType("whisperx")
    fake_wx.load_model = lambda *a, **k: _FakeModel()
    # 130s of audio with quiet dips at the 60s and 120s boundaries -> 3 chunks
    audio = np.ones(int(SR * 130), dtype=np.float32)
    audio[SR * 60 - 2000:SR * 60 + 2000] = 0.0
    audio[SR * 120 - 2000:SR * 120 + 2000] = 0.0
    fake_wx.load_audio = lambda p: audio
    monkeypatch.setitem(sys.modules, "whisperx", fake_wx)

    # chunk every 1 minute, fast mode
    t = WhisperXTranscriber(model_size="small", hf_token="", diarize=False, chunk_minutes=1)
    stages: list[str] = []
    res = t.transcribe(Path("long.webm"), on_stage=stages.append)

    assert len(calls) == 3                       # split into 3 chunks
    assert len(res.segments) == 3                # one segment per chunk, concatenated
    starts = [s.start_ms for s in res.segments]
    assert starts[0] == 0                        # first chunk not offset
    assert starts == sorted(starts) and len(set(starts)) == 3   # strictly increasing offsets
    assert starts[1] > 50_000                    # ~60s offset applied to chunk 2
    assert "transcribing:1/3" in stages and "transcribing:3/3" in stages
    assert "loading" in stages
