# V2M — Chunked transcription for long recordings (fast mode)

## Problem

On the target machine (AMD CPU, no NVIDIA GPU), transcription speed degrades
super-linearly with recording length. Measured fast mode (`V2M_DIARIZE=false`,
`large-v3-turbo`, `batch=32`, silero VAD):

- 1.85-hour recording → RTF ~0.28 (~17 min/hr)
- 4.6-hour recording → RTF ~0.49 (~29 min/hr)

The longer recording is ~1.75× slower per unit of audio. Likely causes: thermal
throttling under sustained multi-hour all-core load, and growing transient memory
(VAD segments + batched features + decode buffers held for the whole file at once).

## Goal

Split a long recording into ~1-hour chunks, transcribe each chunk sequentially,
offset timestamps, and concatenate into one transcript — to **bound peak transient
memory**, **report per-chunk progress**, and **isolate per-chunk faults**.

### Non-goals / honest expectations

- This does **not** fix thermal throttling — chunks run back-to-back, so the CPU
  stays hot. If the slowdown is thermal-dominated, wall-clock barely improves.
- The raw audio array (loaded whole by `whisperx.load_audio`, ~1 GB for 4.6 h)
  still resides in memory. The savings are in the **downstream transient buffers**,
  which are bounded to one chunk instead of accumulating across the whole file.
- No partial-result storage. No cross-chunk speaker identity.

## Key decisions

1. **Fast mode only** (`V2M_DIARIZE=false`). With diarization on, each chunk
   independently emits `SPEAKER_00, 01…` and chunk 2's `SPEAKER_00` is not
   guaranteed to be chunk 1's — global speaker identity needs embedding matching,
   which is hard and is itself the slow stage we are avoiding. In fast mode every
   segment is `SPEAKER_00`, so concatenation is trivially correct. With
   `diarize=true` the transcriber takes the existing single-pass path unchanged.
2. **Silence-aware boundaries.** A hard cut at exactly 60 min can split a word
   across two chunks. Instead, search a ±30 s window around each target boundary
   for the lowest-energy (quietest) point and cut there.
3. **Whole-job failure.** If any chunk raises, the exception propagates and the
   existing job handler marks the whole recording `failed` (retry restarts from the
   beginning). No partial transcript is saved.

## Architecture

The chunking logic lives entirely inside `WhisperXTranscriber._run`. The
`Transcriber` protocol (`transcribe(audio_path, language, on_stage)`) is unchanged,
so `app/jobs/queue.py`, `app/store/repo.py`, the API routes, and `FakeTranscriber`
are **not touched**. The existing test suite continues to pass unmodified.

### Components

**`app/transcribe/chunking.py`** (new, pure, torch-free):

```python
def plan_chunk_windows(audio, sample_rate, chunk_sec, search_sec=30):
    """Return a list of (start_sample, end_sample) windows covering `audio`.

    Cut points fall at the lowest-RMS-energy frame within ±search_sec of each
    chunk_sec boundary, so chunks split on silence rather than mid-utterance.
    Audio shorter than chunk_sec returns a single full-length window.
    """
```

Pure NumPy — unit-testable without torch/whisperx. Covers: short audio → single
window; exact multiples; quietest-point selection within the search window;
contiguous, gap-free, non-overlapping coverage.

**`WhisperXTranscriber._run`** (modified): after `load_audio`, when
`not self.diarize and chunk_sec > 0 and duration > chunk_sec`, plan windows and
loop:

```python
windows = plan_chunk_windows(audio, sr, chunk_sec)
for i, (a, b) in enumerate(windows):
    on_stage(f"transcribing:{i+1}/{len(windows)}")
    r = model.transcribe(audio[a:b], batch_size=self.batch_size, language=forced)
    offset_ms = a / sr * 1000
    # append r["segments"], adding offset_ms to each start/end
```

Segments accumulate with their start/end shifted by the chunk's start offset, so
timestamps are global. The non-chunked branch (short audio, or `diarize=true`) is
the existing single-pass code, unchanged. The per-stage timing line aggregates STT
time across chunks.

**`app/core/config.py`**: add `chunk_minutes: int = 60` to `Settings`.
`app/main.py::_default_transcriber` passes it to `WhisperXTranscriber`, whose new
`chunk_minutes: int = 60` constructor param is stored and converted to seconds
(`chunk_sec = chunk_minutes * 60`) internally. `0` disables chunking.

**`server/.env.example`**: document `V2M_CHUNK_MINUTES` (default 60, 0 = off,
fast-mode only, only applies when the recording is longer than the chunk length).

**`web/src/lib/format.ts`**: `stageLabel` parses the `transcribing:k/n` form and
renders e.g. "전사 중 (2/5)". Plain `transcribing` still renders "전사 중".

### Data flow

```
load_audio(file) -> audio (whole)
  duration > chunk_sec and fast mode?
    yes -> plan_chunk_windows (silence-aware)
            for each window:
              on_stage("transcribing:i/n")
              model.transcribe(audio[a:b])  -> offset timestamps -> accumulate
    no  -> existing single-pass transcribe (incl. all diarize=true cases)
  -> TranscriptResult(segments, full_text=joined, language)
```

## Error handling

- Any chunk exception propagates out of `transcribe()` → caught by
  `queue.run_transcription`'s existing `except` → recording marked `failed` with a
  friendly message, stage cleared. Consistent with current single-pass behavior.
- Timestamp offset is computed from sample index (`a / sr`), independent of the
  chunk's internal clock, so concatenated timestamps are monotonic.

## Testing

- **`chunking.py`**: unit tests, no torch — single-window for short audio, exact
  multiples, quietest-point cut within the search window, gap-free/non-overlapping
  contiguous coverage, and that cut points land near (not necessarily exactly at)
  the target boundary.
- **`test_app_wiring.py`**: assert `WhisperXTranscriber` stores `chunk_minutes`
  (default 60) without importing torch.
- Queue/API/Fake paths are unchanged, so their existing tests pass as-is.
- The chunk-loop glue inside `_run` needs torch and is not unit-tested directly —
  the same known limitation as the existing segment-mapping code. The split logic
  it depends on is fully covered by the pure `chunking.py` tests.

## Config summary

| Setting | Default | Effect |
|---|---|---|
| `V2M_CHUNK_MINUTES` | `60` | Chunk length in minutes. `0` disables chunking. Only applies in fast mode (`V2M_DIARIZE=false`) and only when the recording is longer than this. |
