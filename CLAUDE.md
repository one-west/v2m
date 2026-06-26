# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

V2M (Voice to Minutes) — a personal, **local-first, $0** tool: record meeting audio in the browser → transcribe locally with WhisperX (speaker diarization + timestamps) → produce a speaker-labeled transcript plus a ready-to-paste prompt for **claude.ai** (the formatting/"정형화" step happens in the user's claude.ai subscription, **not** in the app). Runs entirely on the user's PC (localhost); the whole record→transcribe flow works offline.

Design rationale and all product decisions live in [docs/superpowers/specs/v2m-voice-to-minutes-design.md](docs/superpowers/specs/v2m-voice-to-minutes-design.md). The backend was built task-by-task from [docs/superpowers/plans/v2m-backend.md](docs/superpowers/plans/v2m-backend.md).

**Status:** backend complete (`server/`) and frontend complete (`web/` — Vite + React + TS SPA: browser recorder, meeting-info form, transcript UI, copy-for-claude.ai, md/txt export). The frontend consumes the stable `/api` + `/health` contract and is built to `web/dist` (served at `/`). The backend stores optional meeting metadata (`Recording.meta`) and injects a `회의 정보` block into the prompt/export. Frontend design + plan: [docs/superpowers/specs/v2m-frontend-design.md](docs/superpowers/specs/v2m-frontend-design.md), [docs/superpowers/plans/v2m-frontend.md](docs/superpowers/plans/v2m-frontend.md).

## Commands

**One-command dev (recommended):** from the repo root, `npm install` once, then `npm run dev` runs backend (`:8000`) + frontend (`:5173`) together via `concurrently`. The launcher runs the backend with `server/.venv-ml` (the Python 3.12 real-transcription venv) — create that venv first (see README).

### Backend (`server/`, with its venv)

On Windows use the venv's python explicitly (do not rely on a globally-activated env):

```bash
# from server/
.venv/Scripts/python.exe -m pytest -q                         # full suite (53 tests)
.venv/Scripts/python.exe -m pytest tests/test_repo.py -v       # one file
.venv/Scripts/python.exe -m pytest tests/test_jobs.py::test_success_path_sets_done_with_transcript -v  # one test
.venv/Scripts/python.exe -m pip install -e ".[dev]"            # base + dev deps (NO torch — tests don't need it)
.venv/Scripts/python.exe -m pip install -e ".[dev,ml]"         # add whisperx/torch for REAL transcription
python run.py                                                  # serve on http://127.0.0.1:<V2M_PORT>
```

### Frontend (`web/`)

```bash
# from web/
npm test                              # full Vitest suite (27 tests)
npm test -- src/features/recordings   # subset (path filter; Vitest does NOT type-check)
npm run build                         # tsc --noEmit (type gate) + vite build → web/dist (backend serves at /)
npm run dev                           # Vite dev server :5173, proxies /api + /health to :8000
```

Tests run **without** `torch`/`whisperx` installed — see the invariant below. Real transcription has extra requirements (verified working end-to-end on Windows, 2026-06):
- **Python 3.11–3.12 for the `[ml]` extras.** torch / ctranslate2 (via whisperx) have no 3.13/3.14 wheels yet, so the `[ml]` install fails on newer Python. The app + 39-test suite run fine on any 3.11+ (they use the fake transcriber); only real transcription needs a 3.12 venv.
- **ffmpeg** on PATH — `whisperx.load_audio` shells out to the ffmpeg CLI.
- `V2M_HF_TOKEN` in `server/.env`, and accept the gated terms for **`pyannote/speaker-diarization-community-1`** on Hugging Face (whisperx's current default diarization model — NOT the older `speaker-diarization-3.1`). `WhisperXTranscriber.transcribe` pins this model and sets `HF_HUB_DISABLE_SYMLINKS=1` so Windows model downloads work without Developer Mode.

## Architecture (the parts that span files)

**The Transcriber protocol boundary is the central invariant.** `app/transcribe/base.py` defines a `Transcriber` Protocol (`transcribe(audio_path) -> TranscriptResult`). The real `app/transcribe/whisperx_runner.py` imports `whisperx`/`torch` **lazily inside `transcribe()`**, never at module level. `app/transcribe/fake.py` provides `FakeTranscriber` for tests. Result: importing any module never pulls torch, and the entire suite runs against the fake. `tests/test_app_wiring.py::test_whisperx_module_imports_without_torch` guards this. **Do not add a module-level `import whisperx`/`import torch` anywhere** — it breaks the test-without-ML contract.

**`create_app()` is a factory with injectable dependencies** (`app/main.py`): `create_app(*, engine=None, transcriber=None, shutdown_hook=None)`. It stores `engine`, `transcriber`, `settings`, and `shutdown_hook` on `app.state`; the default transcriber (real WhisperX) is constructed lazily **only when none is injected**. Tests inject `FakeTranscriber` and a no-op `shutdown_hook` via `tests/conftest.py`'s `client` fixture, so production ML and real signals never fire under pytest. Routes/`/health`/`/shutdown` are registered before the static `web/dist` mount so the SPA mount never shadows the API.

**Ingest → background job → read pipeline:** `POST /api/recordings` (`app/api/recordings.py`) saves audio to the app-data dir, creates a `Recording` row (status `recorded`), and schedules `run_transcription` via FastAPI `BackgroundTasks` using `request.app.state.transcriber`/`engine`. `app/jobs/queue.py::run_transcription` drives the state machine `recorded → transcribing → done|failed`, reports coarse progress via an `on_stage` callback threaded into `transcribe(...)` (each stage stored on `Recording.stage`, polled by the UI), maps network/download failures (e.g. interrupted model download → `IncompleteRead`) to a friendly Korean error, **opens a fresh DB session per phase** (so no SQLite connection is held during the long transcribe call), catches all exceptions into `failed`+error, and never raises. Note: under `TestClient`, BackgroundTasks run synchronously after the POST response, which is why tests can assert `status == "done"` right after upload.

**Status state machine** (`app/store/models.py` `RecordingStatus`): `recorded`/`transcribing`/`done`/`failed`. Transcript is stored as a JSON dict (`{segments:[{speaker,start_ms,end_ms,text}], full_text, language}`) on the `Recording` row. The row also carries optional meeting metadata `meta` (a JSON dict: `{date,time,location,attendees,agenda}`, all optional) a per-recording transcription `language` (`ko`/`en`/`auto`/None), and a coarse in-progress `stage` (`loading`/`transcribing`/`aligning`/`diarizing`, cleared when done) — all fully backward-compatible (`None` by default). New nullable columns added after a DB exists are backfilled by `db.init_db`'s forward-only `_RECORDING_ADDED_COLUMNS` migration (`create_all` never alters existing tables). Repo functions (`app/store/repo.py`) each take a `Session`; `set_transcript` also flips status to `done`; `update_recording(*, title=None, meta=None)` applies only the non-`None` fields (backs the `PATCH /api/recordings/{id}` edit endpoint).

**The product's "minutes" step is external.** The app does NOT call any LLM. `app/prompt/builder.py` formats the transcript (consecutive same-speaker segments grouped under `[mm:ss] SPEAKER_xx:` headers) and bundles it with a Korean meeting-minutes instruction; when `meta` is present, `format_meta` injects a `=== 회의 정보 ===` block between the instruction and the transcript so claude.ai sees the meeting context. `GET /api/recordings/{id}/prompt` returns this bundle for the user to paste into the claude.ai desktop app. `app/export/markdown.py` exports the transcript (+ meta block) as md/txt (reusing `format_transcript`/`format_meta`). There is intentionally no in-app minutes storage.

**Frontend SPA** (`web/`, Vite + React + TS, no router/state libraries): view state is just `'home' ↔ {detailId}` in `App.tsx`. A typed `lib/api.ts` wraps the `/api` contract with `fetch` (relative paths only); the recorder lives in **App** (`useRecorder`, `audio/webm;codecs=opus` via `MediaRecorder`) — not in RecorderPanel — so it keeps running across in-tab view changes (RecorderPanel is presentational; a top-bar 정지 indicator shows while recording on the detail view). Each chunk streams into IndexedDB (`lib/recordingStore.ts`) so a recording also survives a reload (sleep/refresh/crash): App detects the buffered session on load and offers to recover (assemble + upload) it, and `useBeforeUnloadGuard` warns before refresh/close while recording; `useRecordings` lists + adaptively polls (3s while any row is active, else 12s); `RecordingDetail` independently polls its own status (3s while `recorded`/`transcribing`, unmount-guarded) and seeds its editable form once per load so polls don't clobber edits. The shared `MeetingForm` drives both the home "새 회의" draft and the detail edit (→ `PATCH`). **`CopyForClaude` is copy-only — it writes the prompt bundle to the clipboard and shows a toast; it deliberately never opens claude.ai** (the design mandates pasting into the desktop app). Styling lives in `web/src/styles.css` as design-system CSS variables (single font, no monospace) — see [docs/superpowers/specs/v2m-frontend-design.md](docs/superpowers/specs/v2m-frontend-design.md) and [.superdesign/design-system.md](.superdesign/design-system.md).

**Config & data location** (`app/core/config.py`, `app/core/paths.py`): settings come from `.env` with the `V2M_` prefix (`V2M_HF_TOKEN`, `V2M_WHISPER_MODEL` default `medium`, `V2M_HOST`, `V2M_PORT`, `V2M_LANGUAGE`, plus transcription perf knobs `V2M_BATCH_SIZE` default `16` and `V2M_CPU_THREADS` default `0`=all cores, and quality knobs `V2M_SUPPRESS_NUMERALS` default `true` (spoken numbers → words) and `V2M_INITIAL_PROMPT` (decoder priming, empty=none) passed as WhisperX `asr_options` at model load, and `V2M_VAD_METHOD` default `silero` (fast VAD; `pyannote` is slower) — VAD only affects speech-segmentation speed, not text quality). `WhisperXTranscriber.transcribe(audio_path, language=None)` **forces the language** for transcription + alignment instead of WhisperX auto-detect (which misfires on quiet/short Korean — e.g. detects `uk` and yields 0 segments). Per recording the language is chosen in the new-meeting form (`ko`/`en`/`auto`) and stored on `Recording.language`; the job passes it through, falling back to the configured `V2M_LANGUAGE` (default `ko`) when a row has none, and `auto`/empty re-enables detection. It also uses `batch_size` (WhisperX's batched inference — its main speedup) + `threads`, **caches the STT model / per-language align model / diarization pipeline on the instance** (create_app builds one long-lived transcriber, so every recording after the first skips model load) and **serializes transcriptions with a lock** (the shared whisperx pipeline mutates/resets `self.tokenizer` per call, so concurrent runs raced into `'NoneType' … sot_sequence`), and prints a per-stage timing line (`load+decode / stt / align / diarize / total`). All writable data (SQLite, audio, models, logs) lives under `%LOCALAPPDATA%\v2m\` (override with `V2M_DATA_DIR`), **never** next to the executable — `get_data_dir()` is deliberately uncached so tests can repoint it per-test.

## Conventions & constraints

- TDD throughout: failing test first, minimal implementation, frequent commits. Tests assert real DB state from fresh sessions, not mocks.
- Python 3.11+. CPU-only torch by default (no CUDA assumption).
- **Desktop-readiness guardrails are intentional** (the app is planned to be wrapped as a pywebview desktop app — see spec §13): configurable port, relative `/api` from the frontend, `/health` readiness endpoint, injectable graceful shutdown, app-data dir. Preserve these when extending.
- Known deferred hardening items (non-blocking for the single-user/localhost MVP, tracked in the spec/ledger): Windows graceful-shutdown only sends a delayed SIGTERM (does not yet drain uvicorn cleanly); no path-containment guard before deleting `audio_path`; `whisperx_runner.transcribe`'s segment-mapping is untested (extract to a pure function to unit-test without torch).
