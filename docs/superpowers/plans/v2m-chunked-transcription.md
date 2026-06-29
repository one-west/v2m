# Chunked Transcription (Fast Mode) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split long recordings into ~1-hour silence-aware chunks, transcribe each sequentially, offset timestamps, and concatenate — to bound peak transient memory and report per-chunk progress (fast mode only).

**Architecture:** A new pure NumPy module (`app/transcribe/chunking.py`) computes silence-aware chunk windows. `WhisperXTranscriber._run` uses it only when `diarize=false`, `chunk_sec>0`, and the recording is longer than one chunk; otherwise the existing single-pass path runs unchanged. The `Transcriber` protocol, the job queue, the repo, the API, and `FakeTranscriber` are untouched.

**Tech Stack:** Python 3.11+ (server), pytest; NumPy (already pulled in by whisperx at runtime; the pure-function tests import it directly); TypeScript + Vitest (web).

## Global Constraints

- **No module-level `import whisperx` / `import torch` anywhere.** whisperx/torch stay lazily imported inside `WhisperXTranscriber._run` / `_get_*`. The new `chunking.py` imports only `numpy` (no torch/whisperx). Guard test: `tests/test_app_wiring.py::test_whisperx_module_imports_without_torch`.
- **Fast mode only:** chunking applies only when `diarize=false`. With `diarize=true`, the existing single-pass path runs unchanged (no chunking).
- **Backward compatible:** `V2M_CHUNK_MINUTES` defaults to `60`; existing behavior for short recordings is unchanged.
- **WhisperX sample rate is 16000 Hz** (whisperx resamples on load). Use a module constant `_SAMPLE_RATE = 16000`.
- Run backend tests with the venv python on Windows: `server/.venv/Scripts/python.exe -m pytest`. Frontend: `npm test` from `web/`.
- Commit messages end with the `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` trailer (omitted from the snippets below for brevity — add it).

---

## File Structure

- **Create** `server/app/transcribe/chunking.py` — pure silence-aware window planner. One responsibility: given an audio array, return `(start, end)` sample windows that split on quiet points near chunk boundaries.
- **Create** `server/tests/test_chunking.py` — unit tests for the planner (no torch).
- **Modify** `server/app/core/config.py` — add `chunk_minutes` setting.
- **Modify** `server/app/transcribe/whisperx_runner.py` — add `chunk_minutes` ctor param + `_SAMPLE_RATE`; route fast mode through the chunk loop in `_run`.
- **Modify** `server/app/main.py` — pass `chunk_minutes` to the default transcriber.
- **Modify** `server/.env.example` — document `V2M_CHUNK_MINUTES`.
- **Modify** `server/tests/test_config.py`, `server/tests/test_app_wiring.py`, `server/tests/test_whisperx_runner.py` — tests.
- **Modify** `web/src/lib/format.ts` + `web/src/lib/format.test.ts` — render `transcribing:k/n` progress.

---

## Task 1: Pure silence-aware chunk planner

**Files:**
- Create: `server/app/transcribe/chunking.py`
- Test: `server/tests/test_chunking.py`

**Interfaces:**
- Consumes: nothing (pure NumPy).
- Produces: `plan_chunk_windows(audio, sample_rate: int, chunk_sec: float, search_sec: float = 30) -> list[tuple[int, int]]` — contiguous, gap-free, non-overlapping `(start_sample, end_sample)` windows covering the whole array; cut points land at the lowest-RMS-energy frame within `±search_sec` of each `chunk_sec` boundary. Audio at or shorter than one chunk returns `[(0, len(audio))]`.

- [ ] **Step 1: Write the failing tests**

Create `server/tests/test_chunking.py`:

```python
import numpy as np

from app.transcribe.chunking import plan_chunk_windows


def test_short_audio_returns_single_window():
    audio = np.ones(50, dtype=np.float32)
    assert plan_chunk_windows(audio, sample_rate=100, chunk_sec=1) == [(0, 50)]


def test_audio_exactly_one_chunk_is_single_window():
    audio = np.ones(100, dtype=np.float32)
    assert plan_chunk_windows(audio, sample_rate=100, chunk_sec=1) == [(0, 100)]


def test_zero_chunk_sec_returns_single_window():
    audio = np.ones(500, dtype=np.float32)
    assert plan_chunk_windows(audio, sample_rate=100, chunk_sec=0) == [(0, 500)]


def test_cuts_at_quiet_point_and_covers_contiguously():
    sr = 100
    audio = np.ones(250, dtype=np.float32)
    # quiet dips near the 100- and 200-sample chunk boundaries
    audio[88:96] = 0.0
    audio[188:196] = 0.0
    windows = plan_chunk_windows(audio, sample_rate=sr, chunk_sec=1, search_sec=0.3)

    # full, contiguous, gap-free, non-overlapping coverage
    assert windows[0][0] == 0
    assert windows[-1][1] == 250
    for (a, b), (c, d) in zip(windows, windows[1:]):
        assert b == c
    # the first cut lands inside the first quiet dip (not at the hard 100 mark)
    first_cut = windows[0][1]
    assert 88 <= first_cut < 96
    # more than one window for >1-chunk audio
    assert len(windows) >= 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `server/.venv/Scripts/python.exe -m pytest tests/test_chunking.py -v` (from `server/`)
Expected: FAIL — `ModuleNotFoundError: No module named 'app.transcribe.chunking'`.

- [ ] **Step 3: Write minimal implementation**

Create `server/app/transcribe/chunking.py`:

```python
"""Pure, torch-free helpers for splitting long audio into chunk windows.

Imports only numpy so it stays unit-testable without whisperx/torch.
"""

import numpy as np


def _quietest_point(audio: np.ndarray, lo: int, hi: int, frame: int) -> int:
    """Return the start sample of the lowest-RMS-energy frame in [lo, hi)."""
    best_idx = lo
    best_energy = None
    i = lo
    while i < hi:
        seg = audio[i:min(i + frame, hi)]
        energy = float(np.mean(seg * seg)) if seg.size else float("inf")
        if best_energy is None or energy < best_energy:
            best_energy = energy
            best_idx = i
        i += frame
    return best_idx


def plan_chunk_windows(audio, sample_rate, chunk_sec, search_sec=30):
    """Split `audio` into ~chunk_sec windows that cut on silence.

    Returns contiguous, gap-free (start_sample, end_sample) windows covering the
    whole array. Each interior cut is placed at the quietest frame within
    ±search_sec of the target boundary, so chunks split between utterances rather
    than mid-word. Audio at or shorter than one chunk returns a single window.
    """
    audio = np.asarray(audio, dtype=np.float32)
    n = len(audio)
    chunk = int(chunk_sec * sample_rate)
    if chunk <= 0 or n <= chunk:
        return [(0, n)]

    search = int(search_sec * sample_rate)
    frame = max(1, int(0.02 * sample_rate))  # 20 ms energy frames
    windows: list[tuple[int, int]] = []
    start = 0
    while start < n:
        target = start + chunk
        if target >= n:
            windows.append((start, n))
            break
        lo = max(start + 1, target - search)
        hi = min(n, target + search)
        cut = _quietest_point(audio, lo, hi, frame)
        windows.append((start, cut))
        start = cut
    return windows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `server/.venv/Scripts/python.exe -m pytest tests/test_chunking.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add server/app/transcribe/chunking.py server/tests/test_chunking.py
git commit -m "feat(server): pure silence-aware chunk-window planner"
```

---

## Task 2: Wire `chunk_minutes` through config + transcriber constructor

**Files:**
- Modify: `server/app/core/config.py:29-32` (add setting after `diarize`)
- Modify: `server/app/transcribe/whisperx_runner.py:18-46` (ctor signature + store)
- Modify: `server/app/main.py:17-30` (pass through)
- Modify: `server/.env.example`
- Test: `server/tests/test_config.py`, `server/tests/test_app_wiring.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `Settings.chunk_minutes: int = 60`; `WhisperXTranscriber(..., chunk_minutes: int = 60)` storing `self.chunk_minutes`. Task 3 reads `self.chunk_minutes`.

- [ ] **Step 1: Write the failing tests**

In `server/tests/test_config.py`, add to `test_defaults` (after the `diarize` assert):

```python
    assert s.chunk_minutes == 60
```

In `test_env_override`, add a setenv line and an assert:

```python
    monkeypatch.setenv("V2M_CHUNK_MINUTES", "30")
    # ... after Settings(...) is built:
    assert s.chunk_minutes == 30
```

In `server/tests/test_app_wiring.py::test_whisperx_transcriber_stores_perf_params_without_torch`, add to the defaults block (after `assert d.diarize is True`):

```python
    assert d.chunk_minutes == 60
```

And to the explicit-params block at the top of that test (the `t = WhisperXTranscriber(... batch_size=8 ...)` instance), extend the constructor call with `chunk_minutes=30` and assert:

```python
    t = WhisperXTranscriber(model_size="small", hf_token="", batch_size=8, cpu_threads=4,
                            language="en", chunk_minutes=30)
    assert t.batch_size == 8
    assert t.cpu_threads == 4
    assert t.language == "en"
    assert t.chunk_minutes == 30
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `server/.venv/Scripts/python.exe -m pytest tests/test_config.py tests/test_app_wiring.py -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'chunk_minutes'` / `TypeError: __init__() got an unexpected keyword argument 'chunk_minutes'`.

- [ ] **Step 3: Write minimal implementation**

In `server/app/core/config.py`, add after the `diarize` field (line ~29, before `ffmpeg_dir`):

```python
    # Long-recording chunking (fast mode only): split audio longer than this many
    # minutes into sequential chunks (silence-aware cuts), to bound peak transient
    # memory and report per-chunk progress. 0 disables. Ignored when diarize=true.
    chunk_minutes: int = 60
```

In `server/app/transcribe/whisperx_runner.py`, extend `__init__` — add the param at the end of the signature and store it:

```python
    def __init__(self, model_size: str, hf_token: str, device: str = "cpu",
                 compute_type: str = "int8", ffmpeg_dir: str = "",
                 batch_size: int = 16, cpu_threads: int = 0, language: str = "ko",
                 suppress_numerals: bool = True, initial_prompt: str = "",
                 vad_method: str = "silero", diarize: bool = True,
                 chunk_minutes: int = 60) -> None:
```

Add inside the body (e.g. right after `self.diarize = diarize`):

```python
        self.chunk_minutes = chunk_minutes
```

In `server/app/main.py::_default_transcriber`, add the keyword to the `WhisperXTranscriber(...)` call (after `diarize=settings.diarize,`):

```python
        chunk_minutes=settings.chunk_minutes,
```

In `server/.env.example`, add after the `V2M_DIARIZE` block (before the ffmpeg block):

```
# Long-recording chunking (fast mode only, V2M_DIARIZE=false): recordings longer
# than this many minutes are split into sequential silence-aware chunks — bounds
# peak memory on multi-hour audio and shows per-chunk progress. 0 = disabled.
# Has no effect when V2M_DIARIZE=true.
V2M_CHUNK_MINUTES=60
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `server/.venv/Scripts/python.exe -m pytest tests/test_config.py tests/test_app_wiring.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/app/core/config.py server/app/transcribe/whisperx_runner.py server/app/main.py server/.env.example server/tests/test_config.py server/tests/test_app_wiring.py
git commit -m "feat(server): add V2M_CHUNK_MINUTES setting wired to the transcriber"
```

---

## Task 3: Chunked transcription path in `_run`

**Files:**
- Modify: `server/app/transcribe/whisperx_runner.py` (add `_SAMPLE_RATE` constant near the top; replace the body of `_run`, lines ~98-173)
- Test: `server/tests/test_whisperx_runner.py`

**Interfaces:**
- Consumes: `plan_chunk_windows` from Task 1; `self.chunk_minutes` from Task 2.
- Produces: no signature change — `transcribe(audio_path, language=None, on_stage=None) -> TranscriptResult` still. New behavior: in fast mode on long audio, emits `on_stage("transcribing:k/n")` per chunk and returns concatenated, globally-offset segments.

- [ ] **Step 1: Write the failing test**

In `server/tests/test_whisperx_runner.py`, add (the file already does `import sys, types`; add `import numpy as np` inside the test):

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `server/.venv/Scripts/python.exe -m pytest tests/test_whisperx_runner.py::test_fast_mode_chunks_long_audio_and_offsets_timestamps -v`
Expected: FAIL — only one `transcribe` call (whole audio), no `transcribing:k/n` stages.

- [ ] **Step 3: Write the implementation**

In `server/app/transcribe/whisperx_runner.py`, add a module constant after the imports (before `class WhisperXTranscriber`):

```python
_SAMPLE_RATE = 16000  # whisperx.load_audio resamples to 16 kHz
```

Replace the body of `_run` (everything from `t0 = time.perf_counter()` to the final `return`) with:

```python
        t0 = time.perf_counter()
        stage("loading")
        model = self._get_model()  # cached after the first recording
        audio = whisperx.load_audio(str(audio_path))
        t_load = time.perf_counter()

        # Per-recording `language` overrides the configured default; "auto"/empty/None
        # (with no configured default) => let WhisperX detect.
        chosen = language if language is not None else self.language
        auto = chosen in (None, "", "auto")
        forced = None if auto else chosen

        chunk_sec = self.chunk_minutes * 60
        duration = len(audio) / _SAMPLE_RATE
        # Chunking only helps (and is only correct) in fast mode: every segment is
        # SPEAKER_00 so concatenation is trivial. Diarize mode keeps the single pass.
        chunked = (not self.diarize) and chunk_sec > 0 and duration > chunk_sec

        if chunked:
            from app.transcribe.chunking import plan_chunk_windows

            windows = plan_chunk_windows(audio, _SAMPLE_RATE, chunk_sec)
            n = len(windows)
            final_segments: list = []
            detected = None
            for i, (a, b) in enumerate(windows):
                stage(f"transcribing:{i + 1}/{n}")
                r = model.transcribe(audio[a:b], batch_size=self.batch_size, language=forced)
                if detected is None:
                    detected = r.get("language")
                offset = a / _SAMPLE_RATE  # seconds; mapped to ms in the shared loop below
                for seg in r.get("segments", []):
                    seg = dict(seg)
                    seg["start"] = seg.get("start", 0) + offset
                    seg["end"] = seg.get("end", 0) + offset
                    final_segments.append(seg)
            language = (detected if auto else chosen) or "ko"
            t_stt = t_align = t_diar = time.perf_counter()
        else:
            stage("transcribing")
            # batch_size is WhisperX's core speedup: VAD-chunked segments run in parallel.
            result = model.transcribe(audio, batch_size=self.batch_size, language=forced)
            language = (result.get("language", "ko") if auto else chosen) or "ko"
            t_stt = time.perf_counter()

            # Fast mode (diarize=False): skip alignment + diarization (~90% of CPU
            # time) and use WhisperX's segment-level output directly.
            if self.diarize:
                stage("aligning")
                align_model, metadata = self._get_align(language)  # cached per language
                aligned = whisperx.align(result["segments"], align_model, metadata, audio, self.device)
                t_align = time.perf_counter()

                stage("diarizing")
                diarize_model = self._get_diarize()  # cached after the first recording
                diarize_segments = diarize_model(audio)
                final_segments = whisperx.assign_word_speakers(diarize_segments, aligned).get("segments", [])
                t_diar = time.perf_counter()
            else:
                t_align = t_diar = t_stt
                final_segments = result.get("segments", [])

        print(
            f"[v2m.transcribe] model={self.model_size} batch={self.batch_size} "
            f"threads={self.cpu_threads or 'auto'} lang={language} diarize={self.diarize} "
            f"chunked={chunked} | "
            f"load+decode={t_load - t0:.1f}s stt={t_stt - t_load:.1f}s "
            f"align={t_align - t_stt:.1f}s diarize={t_diar - t_align:.1f}s "
            f"total={t_diar - t0:.1f}s",
            flush=True,
        )

        segments: list[TranscriptSegment] = []
        texts: list[str] = []
        for seg in final_segments:
            text = seg.get("text", "").strip()
            if not text:
                continue
            segments.append(TranscriptSegment(
                speaker=seg.get("speaker", "SPEAKER_00"),
                start_ms=int(seg.get("start", 0) * 1000),
                end_ms=int(seg.get("end", 0) * 1000),
                text=text,
            ))
            texts.append(text)
        return TranscriptResult(segments=segments, full_text=" ".join(texts), language=language)
```

(Note: `model.transcribe(audio[a:b], ...)` slices a NumPy array; `whisperx.load_audio` returns one. The existing fast/diarize/single-pass behavior is preserved for short audio and all `diarize=true` cases.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `server/.venv/Scripts/python.exe -m pytest tests/test_whisperx_runner.py -v`
Expected: PASS — the new chunk test plus all existing ones (`test_fast_mode_skips_align_and_diarize` still sees `["loading", "transcribing"]` because its 1-sample audio is shorter than a chunk).

- [ ] **Step 5: Commit**

```bash
git add server/app/transcribe/whisperx_runner.py server/tests/test_whisperx_runner.py
git commit -m "feat(server): chunk long fast-mode recordings into ~1hr windows"
```

---

## Task 4: Frontend progress label for `transcribing:k/n`

**Files:**
- Modify: `web/src/lib/format.ts:44-47` (`stageLabel`)
- Test: `web/src/lib/format.test.ts`

**Interfaces:**
- Consumes: the backend `stage` string, which may now be `"transcribing:2/5"`.
- Produces: `stageLabel("transcribing:2/5") === "음성 인식 (2/5)"`; plain `"transcribing"` and all other stages unchanged.

- [ ] **Step 1: Write the failing test**

In `web/src/lib/format.test.ts`, inside the `describe("format", ...)` block, add to the stage test (near the existing `stageLabel(...)` asserts):

```typescript
    expect(stageLabel("transcribing:2/5")).toBe("음성 인식 (2/5)");
    expect(stageLabel("transcribing:1/1")).toBe("음성 인식 (1/1)");
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `web/`): `npm test -- src/lib/format.test.ts`
Expected: FAIL — `stageLabel("transcribing:2/5")` returns the raw string `"transcribing:2/5"`.

- [ ] **Step 3: Write the implementation**

In `web/src/lib/format.ts`, replace `stageLabel`:

```typescript
export function stageLabel(stage: string | null): string | null {
  if (!stage) return null;
  // Chunked transcription reports progress as "transcribing:k/n".
  const m = /^transcribing:(\d+)\/(\d+)$/.exec(stage);
  if (m) return `${STAGE_LABELS.transcribing} (${m[1]}/${m[2]})`;
  return STAGE_LABELS[stage] ?? stage;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (from `web/`): `npm test -- src/lib/format.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/format.ts web/src/lib/format.test.ts
git commit -m "feat(web): show per-chunk progress in the transcribing stage label"
```

---

## Task 5: Full-suite verification

**Files:** none (verification only).

- [ ] **Step 1: Backend suite**

Run (from `server/`): `server/.venv/Scripts/python.exe -m pytest -q`
Expected: PASS (existing tests + the new `test_chunking.py` and chunk test; ~57 tests).

- [ ] **Step 2: Frontend suite + type gate**

Run (from `web/`): `npm test` then `npm run build`
Expected: both PASS (Vitest green; `tsc --noEmit` clean).

- [ ] **Step 3: Commit (only if any incidental fixups were needed)**

```bash
git add -A
git commit -m "test: verify chunked-transcription suite green"
```

---

## Self-Review Notes (author)

- **Spec coverage:** §Architecture/components → Tasks 1-4; `chunking.py` pure planner → Task 1; fast-mode-only + duration gate → Task 3 (`chunked = (not self.diarize) and chunk_sec > 0 and duration > chunk_sec`); silence-aware cut → Task 1; whole-job failure → unchanged `queue.run_transcription` (no task needed; exceptions propagate as today); `V2M_CHUNK_MINUTES` config → Task 2; progress `transcribing:k/n` + frontend label → Tasks 3-4; testing plan → Tasks 1-5. Memory-bound caveat is documented behavior, not code.
- **Type consistency:** `plan_chunk_windows(audio, sample_rate, chunk_sec, search_sec=30)` and `chunk_minutes` used identically across Tasks 1-3. `chunk_sec = self.chunk_minutes * 60`. Stage string format `transcribing:{k}/{n}` matches the frontend regex `^transcribing:(\d+)\/(\d+)$`.
- **No placeholders:** all steps contain runnable code/commands and expected output.
