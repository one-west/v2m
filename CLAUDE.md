# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

V2M (Voice to Minutes) — a personal, **local-first, $0** tool: record meeting audio in the browser → transcribe locally with WhisperX (speaker diarization + timestamps) → produce a speaker-labeled transcript plus a ready-to-paste prompt for **claude.ai** (the formatting/"정형화" step happens in the user's claude.ai subscription, **not** in the app). Runs entirely on the user's PC (localhost); the whole record→transcribe flow works offline.

Design rationale and all product decisions live in [docs/superpowers/specs/v2m-voice-to-minutes-design.md](docs/superpowers/specs/v2m-voice-to-minutes-design.md). The backend was built task-by-task from [docs/superpowers/plans/v2m-backend.md](docs/superpowers/plans/v2m-backend.md).

**Status:** backend complete (`server/`). Frontend (browser recorder + transcript UI + claude.ai copy) is **not built yet** — it's "Plan B" and will consume the stable `/api` + `/health` contract.

## Commands

All backend work happens in `server/` with its venv. On Windows use the venv's python explicitly (do not rely on a globally-activated env):

```bash
# from server/
.venv/Scripts/python.exe -m pytest -q                         # full suite (39 tests)
.venv/Scripts/python.exe -m pytest tests/test_repo.py -v       # one file
.venv/Scripts/python.exe -m pytest tests/test_jobs.py::test_success_path_sets_done_with_transcript -v  # one test
.venv/Scripts/python.exe -m pip install -e ".[dev]"            # base + dev deps (NO torch — tests don't need it)
.venv/Scripts/python.exe -m pip install -e ".[dev,ml]"         # add whisperx/torch for REAL transcription
python run.py                                                  # serve on http://127.0.0.1:<V2M_PORT>
```

Tests run **without** `torch`/`whisperx` installed — see the invariant below. Real transcription additionally needs **ffmpeg** on PATH and `V2M_HF_TOKEN` in `server/.env` (accept terms for `pyannote/segmentation-3.0` and `pyannote/speaker-diarization-3.1` on Hugging Face first).

## Architecture (the parts that span files)

**The Transcriber protocol boundary is the central invariant.** `app/transcribe/base.py` defines a `Transcriber` Protocol (`transcribe(audio_path) -> TranscriptResult`). The real `app/transcribe/whisperx_runner.py` imports `whisperx`/`torch` **lazily inside `transcribe()`**, never at module level. `app/transcribe/fake.py` provides `FakeTranscriber` for tests. Result: importing any module never pulls torch, and the entire suite runs against the fake. `tests/test_app_wiring.py::test_whisperx_module_imports_without_torch` guards this. **Do not add a module-level `import whisperx`/`import torch` anywhere** — it breaks the test-without-ML contract.

**`create_app()` is a factory with injectable dependencies** (`app/main.py`): `create_app(*, engine=None, transcriber=None, shutdown_hook=None)`. It stores `engine`, `transcriber`, `settings`, and `shutdown_hook` on `app.state`; the default transcriber (real WhisperX) is constructed lazily **only when none is injected**. Tests inject `FakeTranscriber` and a no-op `shutdown_hook` via `tests/conftest.py`'s `client` fixture, so production ML and real signals never fire under pytest. Routes/`/health`/`/shutdown` are registered before the static `web/dist` mount so the SPA mount never shadows the API.

**Ingest → background job → read pipeline:** `POST /api/recordings` (`app/api/recordings.py`) saves audio to the app-data dir, creates a `Recording` row (status `recorded`), and schedules `run_transcription` via FastAPI `BackgroundTasks` using `request.app.state.transcriber`/`engine`. `app/jobs/queue.py::run_transcription` drives the state machine `recorded → transcribing → done|failed`, **opens a fresh DB session per phase** (so no SQLite connection is held during the long transcribe call), catches all exceptions into `failed`+error, and never raises. Note: under `TestClient`, BackgroundTasks run synchronously after the POST response, which is why tests can assert `status == "done"` right after upload.

**Status state machine** (`app/store/models.py` `RecordingStatus`): `recorded`/`transcribing`/`done`/`failed`. Transcript is stored as a JSON dict (`{segments:[{speaker,start_ms,end_ms,text}], full_text, language}`) on the `Recording` row. Repo functions (`app/store/repo.py`) each take a `Session`; `set_transcript` also flips status to `done`.

**The product's "minutes" step is external.** The app does NOT call any LLM. `app/prompt/builder.py` formats the transcript (consecutive same-speaker segments grouped under `[mm:ss] SPEAKER_xx:` headers) and bundles it with a Korean meeting-minutes instruction; `GET /api/recordings/{id}/prompt` returns this for the user to paste into claude.ai. `app/export/markdown.py` exports the transcript as md/txt (reusing `format_transcript`). There is intentionally no in-app minutes storage.

**Config & data location** (`app/core/config.py`, `app/core/paths.py`): settings come from `.env` with the `V2M_` prefix (`V2M_HF_TOKEN`, `V2M_WHISPER_MODEL` default `medium`, `V2M_HOST`, `V2M_PORT`, `V2M_LANGUAGE`). All writable data (SQLite, audio, models, logs) lives under `%LOCALAPPDATA%\v2m\` (override with `V2M_DATA_DIR`), **never** next to the executable — `get_data_dir()` is deliberately uncached so tests can repoint it per-test.

## Conventions & constraints

- TDD throughout: failing test first, minimal implementation, frequent commits. Tests assert real DB state from fresh sessions, not mocks.
- Python 3.11+. CPU-only torch by default (no CUDA assumption).
- **Desktop-readiness guardrails are intentional** (the app is planned to be wrapped as a pywebview desktop app — see spec §13): configurable port, relative `/api` from the frontend, `/health` readiness endpoint, injectable graceful shutdown, app-data dir. Preserve these when extending.
- Known deferred hardening items (non-blocking for the single-user/localhost MVP, tracked in the spec/ledger): Windows graceful-shutdown only sends a delayed SIGTERM (does not yet drain uvicorn cleanly); no path-containment guard before deleting `audio_path`; `whisperx_runner.transcribe`'s segment-mapping is untested (extract to a pure function to unit-test without torch).
