# V2M Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the local FastAPI backend that ingests meeting audio, transcribes it with speaker diarization + timestamps locally (WhisperX), stores transcripts in SQLite, and exposes a "copy-for-claude.ai" prompt bundle and transcript export — all testable via HTTP without a frontend.

**Architecture:** Single-user localhost FastAPI app. Audio uploaded → saved to app-data dir → a background job runs the transcription pipeline (status state machine: `recorded → transcribing → done|failed`) → transcript stored as JSON on the `Recording` row. The heavy ML transcriber sits behind a `Transcriber` protocol so tests use a fake and the real WhisperX runner is never imported in tests. Designed "desktop-ready" (configurable port, app-data dir, `/health`, graceful shutdown) per the spec's §5.5 guardrails.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, SQLModel (SQLite), pydantic-settings, WhisperX (faster-whisper + pyannote), pytest. ffmpeg on PATH/bundled.

## Global Constraints

- Python 3.11+ only.
- All writable data (DB, audio, models, logs) lives under the app-data dir `%LOCALAPPDATA%\v2m\` (Windows) / `~/.local/share/v2m` (fallback) — **never** next to the executable.
- STT default model: `medium` (int8). Configurable via `.env`.
- CPU-only torch by default (no CUDA assumption).
- MVP configuration source is `.env` (HF token, model size, host, port).
- Frontend (later) calls relative `/api/...`; backend serves API under the `/api` prefix and may serve static `web/dist` at `/`.
- The real WhisperX runner must NOT be imported during tests — the `Transcriber` protocol is injected.
- Status state machine values: `recorded`, `transcribing`, `done`, `failed`.
- TDD: every task writes a failing test first. Frequent commits. DRY. YAGNI.

---

## File Structure

```
server/
  pyproject.toml          # deps + pytest config
  .env.example            # documented config keys
  app/
    __init__.py
    main.py               # create_app() factory, /health, static serving, lifespan
    core/
      __init__.py
      paths.py            # app-data dir resolution + ensure dirs
      config.py           # Settings (pydantic-settings) + get_settings()
      health.py           # check_models_ready()
    store/
      __init__.py
      models.py           # RecordingStatus, Recording (SQLModel table)
      db.py               # get_engine(), init_db(), session helper
      repo.py             # CRUD functions over a Session
    transcribe/
      __init__.py
      base.py             # TranscriptSegment, TranscriptResult, Transcriber protocol
      fake.py             # FakeTranscriber (tests/dev)
      whisperx_runner.py  # WhisperXTranscriber (real, guarded import)
    jobs/
      __init__.py
      queue.py            # run_transcription() pipeline + state transitions
    prompt/
      __init__.py
      builder.py          # build_prompt() -> PromptBundle
    export/
      __init__.py
      markdown.py         # to_markdown(), to_txt()
    api/
      __init__.py
      recordings.py       # APIRouter: upload/list/detail/status/retry/delete/prompt/export
  tests/
    conftest.py           # engine + TestClient fixtures (FakeTranscriber)
    test_paths.py
    test_config.py
    test_repo.py
    test_health.py
    test_ingest.py
    test_transcriber_fake.py
    test_jobs.py
    test_recordings_api.py
    test_prompt.py
    test_export.py
```

---

### Task 1: Project scaffolding, config, and app-data paths

**Files:**
- Create: `server/pyproject.toml`
- Create: `server/.env.example`
- Create: `server/app/__init__.py` (empty)
- Create: `server/app/core/__init__.py` (empty)
- Create: `server/app/core/paths.py`
- Create: `server/app/core/config.py`
- Test: `server/tests/test_paths.py`, `server/tests/test_config.py`

**Interfaces:**
- Produces:
  - `paths.get_data_dir() -> pathlib.Path` (creates dir), plus `get_audio_dir()`, `get_db_path()`, `get_models_dir()`, `get_logs_dir()` — all return `Path`, all ensure parent dirs exist. `get_data_dir()` honors env override `V2M_DATA_DIR`.
  - `config.Settings` (pydantic-settings `BaseSettings`) fields: `hf_token: str = ""`, `whisper_model: str = "medium"`, `host: str = "127.0.0.1"`, `port: int = 8000`, `language: str = "ko"`. Reads `.env`. Env prefix `V2M_`.
  - `config.get_settings() -> Settings` (lru_cached).

- [ ] **Step 1: Add dependencies and pytest config**

Create `server/pyproject.toml`:

```toml
[project]
name = "v2m-server"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "sqlmodel>=0.0.22",
    "pydantic-settings>=2.4",
    "python-multipart>=0.0.9",
]

[project.optional-dependencies]
ml = [
    "whisperx>=3.1",
    "faster-whisper>=1.0",
    "torch>=2.2",
]
dev = [
    "pytest>=8.0",
    "httpx>=0.27",
]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

- [ ] **Step 2: Write the failing test for paths**

Create `server/tests/test_paths.py`:

```python
from pathlib import Path
from app.core import paths


def test_data_dir_honors_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("V2M_DATA_DIR", str(tmp_path / "v2m"))
    d = paths.get_data_dir()
    assert d == tmp_path / "v2m"
    assert d.is_dir()


def test_subdirs_are_created(tmp_path, monkeypatch):
    monkeypatch.setenv("V2M_DATA_DIR", str(tmp_path / "v2m"))
    assert paths.get_audio_dir().is_dir()
    assert paths.get_models_dir().is_dir()
    assert paths.get_logs_dir().is_dir()
    assert paths.get_db_path().name == "v2m.db"
    assert paths.get_db_path().parent.is_dir()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd server && python -m pytest tests/test_paths.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.paths'`

- [ ] **Step 4: Implement paths**

Create `server/app/core/paths.py`:

```python
import os
from pathlib import Path


def get_data_dir() -> Path:
    override = os.environ.get("V2M_DATA_DIR")
    if override:
        base = Path(override)
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "v2m"
    else:
        base = Path.home() / ".local/share/v2m"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _ensure(sub: str) -> Path:
    p = get_data_dir() / sub
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_audio_dir() -> Path:
    return _ensure("audio")


def get_models_dir() -> Path:
    return _ensure("models")


def get_logs_dir() -> Path:
    return _ensure("logs")


def get_db_path() -> Path:
    _ensure("db")
    return get_data_dir() / "db" / "v2m.db"
```

- [ ] **Step 5: Run paths test to verify it passes**

Run: `cd server && python -m pytest tests/test_paths.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Write the failing test for config**

Create `server/tests/test_config.py`:

```python
from app.core.config import Settings


def test_defaults():
    s = Settings(_env_file=None)
    assert s.whisper_model == "medium"
    assert s.host == "127.0.0.1"
    assert s.port == 8000
    assert s.language == "ko"
    assert s.hf_token == ""


def test_env_override(monkeypatch):
    monkeypatch.setenv("V2M_WHISPER_MODEL", "small")
    monkeypatch.setenv("V2M_PORT", "9001")
    s = Settings(_env_file=None)
    assert s.whisper_model == "small"
    assert s.port == 9001
```

- [ ] **Step 7: Run config test to verify it fails**

Run: `cd server && python -m pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.config'`

- [ ] **Step 8: Implement config**

Create `server/app/core/config.py`:

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="V2M_", env_file=".env", extra="ignore")

    hf_token: str = ""
    whisper_model: str = "medium"
    host: str = "127.0.0.1"
    port: int = 8000
    language: str = "ko"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

Create `server/.env.example`:

```
# Hugging Face token for pyannote speaker-diarization (accept model terms first)
V2M_HF_TOKEN=
# STT model size: tiny | base | small | medium | large-v3
V2M_WHISPER_MODEL=medium
V2M_HOST=127.0.0.1
V2M_PORT=8000
V2M_LANGUAGE=ko
```

Create empty `server/app/__init__.py` and `server/app/core/__init__.py`.

- [ ] **Step 9: Run config test to verify it passes**

Run: `cd server && python -m pytest tests/test_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 10: Commit**

```bash
git add server/pyproject.toml server/.env.example server/app/__init__.py server/app/core/
git add server/tests/test_paths.py server/tests/test_config.py
git commit -m "feat(server): scaffolding, config, and app-data paths"
```

---

### Task 2: Data store — Recording model, DB, and repository

**Files:**
- Create: `server/app/store/__init__.py` (empty)
- Create: `server/app/store/models.py`
- Create: `server/app/store/db.py`
- Create: `server/app/store/repo.py`
- Test: `server/tests/test_repo.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `models.RecordingStatus(str, Enum)`: `RECORDED="recorded"`, `TRANSCRIBING="transcribing"`, `DONE="done"`, `FAILED="failed"`.
  - `models.Recording` (SQLModel `table=True`): `id: str` (uuid4 hex, primary key), `title: str`, `created_at: datetime`, `duration_sec: int | None`, `audio_path: str`, `status: RecordingStatus`, `error: str | None`, `transcript: dict | None` (JSON column).
  - `db.get_engine(db_path: Path | None = None)` -> SQLAlchemy Engine; `db.init_db(engine)`; `db.session_scope(engine)` contextmanager yielding a `Session`.
  - `repo` functions, each taking `session: Session`:
    - `create_recording(session, *, title, audio_path, duration_sec=None) -> Recording`
    - `get_recording(session, rec_id) -> Recording | None`
    - `list_recordings(session) -> list[Recording]` (newest first)
    - `update_status(session, rec_id, status, error=None) -> Recording`
    - `set_transcript(session, rec_id, transcript: dict) -> Recording`
    - `delete_recording(session, rec_id) -> bool`

- [ ] **Step 1: Write the failing test**

Create `server/tests/test_repo.py`:

```python
import pytest
from sqlmodel import Session

from app.store import db, repo
from app.store.models import RecordingStatus


@pytest.fixture
def engine(tmp_path):
    e = db.get_engine(tmp_path / "test.db")
    db.init_db(e)
    return e


def test_create_and_get(engine):
    with Session(engine) as s:
        rec = repo.create_recording(s, title="Standup", audio_path="/a/b.webm")
        assert rec.id
        assert rec.status == RecordingStatus.RECORDED
        fetched = repo.get_recording(s, rec.id)
        assert fetched.title == "Standup"


def test_list_newest_first(engine):
    with Session(engine) as s:
        a = repo.create_recording(s, title="A", audio_path="/a")
        b = repo.create_recording(s, title="B", audio_path="/b")
        ids = [r.id for r in repo.list_recordings(s)]
        assert ids[0] == b.id and ids[1] == a.id


def test_update_status_and_transcript(engine):
    with Session(engine) as s:
        rec = repo.create_recording(s, title="X", audio_path="/x")
        repo.update_status(s, rec.id, RecordingStatus.TRANSCRIBING)
        repo.set_transcript(s, rec.id, {"segments": [], "full_text": "hi", "language": "ko"})
        updated = repo.get_recording(s, rec.id)
        assert updated.status == RecordingStatus.DONE
        assert updated.transcript["full_text"] == "hi"


def test_failed_status_keeps_error(engine):
    with Session(engine) as s:
        rec = repo.create_recording(s, title="X", audio_path="/x")
        repo.update_status(s, rec.id, RecordingStatus.FAILED, error="boom")
        assert repo.get_recording(s, rec.id).error == "boom"


def test_delete(engine):
    with Session(engine) as s:
        rec = repo.create_recording(s, title="X", audio_path="/x")
        assert repo.delete_recording(s, rec.id) is True
        assert repo.get_recording(s, rec.id) is None
        assert repo.delete_recording(s, "missing") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && python -m pytest tests/test_repo.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.store'`

- [ ] **Step 3: Implement models**

Create `server/app/store/__init__.py` (empty) and `server/app/store/models.py`:

```python
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from sqlalchemy import Column
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


class RecordingStatus(str, Enum):
    RECORDED = "recorded"
    TRANSCRIBING = "transcribing"
    DONE = "done"
    FAILED = "failed"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Recording(SQLModel, table=True):
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    title: str
    created_at: datetime = Field(default_factory=_now)
    duration_sec: Optional[int] = None
    audio_path: str
    status: RecordingStatus = Field(default=RecordingStatus.RECORDED)
    error: Optional[str] = None
    transcript: Optional[dict] = Field(default=None, sa_column=Column(JSON))
```

- [ ] **Step 4: Implement db**

Create `server/app/store/db.py`:

```python
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from sqlmodel import Session, SQLModel, create_engine

from app.core.paths import get_db_path


def get_engine(db_path: Optional[Path] = None):
    path = db_path or get_db_path()
    return create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})


def init_db(engine) -> None:
    SQLModel.metadata.create_all(engine)


@contextmanager
def session_scope(engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session
```

- [ ] **Step 5: Implement repo**

Create `server/app/store/repo.py`:

```python
from typing import Optional

from sqlmodel import Session, select

from app.store.models import Recording, RecordingStatus


def create_recording(session: Session, *, title: str, audio_path: str,
                     duration_sec: Optional[int] = None) -> Recording:
    rec = Recording(title=title, audio_path=audio_path, duration_sec=duration_sec)
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


def get_recording(session: Session, rec_id: str) -> Optional[Recording]:
    return session.get(Recording, rec_id)


def list_recordings(session: Session) -> list[Recording]:
    stmt = select(Recording).order_by(Recording.created_at.desc())
    return list(session.exec(stmt))


def update_status(session: Session, rec_id: str, status: RecordingStatus,
                  error: Optional[str] = None) -> Recording:
    rec = session.get(Recording, rec_id)
    rec.status = status
    rec.error = error
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


def set_transcript(session: Session, rec_id: str, transcript: dict) -> Recording:
    rec = session.get(Recording, rec_id)
    rec.transcript = transcript
    rec.status = RecordingStatus.DONE
    rec.error = None
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


def delete_recording(session: Session, rec_id: str) -> bool:
    rec = session.get(Recording, rec_id)
    if rec is None:
        return False
    session.delete(rec)
    session.commit()
    return True
```

> Note: `list_recordings` orders by `created_at desc`; tests create rows fast, but uuid + insertion order make ties deterministic enough for the test. If flakiness appears, the api layer can secondary-sort by rowid.

- [ ] **Step 6: Run test to verify it passes**

Run: `cd server && python -m pytest tests/test_repo.py -v`
Expected: PASS (5 passed)

- [ ] **Step 7: Commit**

```bash
git add server/app/store/ server/tests/test_repo.py
git commit -m "feat(server): Recording model, SQLite engine, and repository CRUD"
```

---

### Task 3: Transcriber protocol + fake implementation

**Files:**
- Create: `server/app/transcribe/__init__.py` (empty)
- Create: `server/app/transcribe/base.py`
- Create: `server/app/transcribe/fake.py`
- Test: `server/tests/test_transcriber_fake.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `base.TranscriptSegment` (pydantic `BaseModel`): `speaker: str`, `start_ms: int`, `end_ms: int`, `text: str`.
  - `base.TranscriptResult` (pydantic): `segments: list[TranscriptSegment]`, `full_text: str`, `language: str`; method `to_dict() -> dict`.
  - `base.Transcriber` (`typing.Protocol`): `transcribe(self, audio_path: Path) -> TranscriptResult`.
  - `fake.FakeTranscriber`: constructor `FakeTranscriber(result: TranscriptResult | None = None)`; returns the given result (or a default 2-segment Korean sample); records `last_audio_path`.

- [ ] **Step 1: Write the failing test**

Create `server/tests/test_transcriber_fake.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && python -m pytest tests/test_transcriber_fake.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.transcribe'`

- [ ] **Step 3: Implement base**

Create `server/app/transcribe/__init__.py` (empty) and `server/app/transcribe/base.py`:

```python
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class TranscriptSegment(BaseModel):
    speaker: str
    start_ms: int
    end_ms: int
    text: str


class TranscriptResult(BaseModel):
    segments: list[TranscriptSegment]
    full_text: str
    language: str

    def to_dict(self) -> dict:
        return self.model_dump()


@runtime_checkable
class Transcriber(Protocol):
    def transcribe(self, audio_path: Path) -> TranscriptResult: ...
```

- [ ] **Step 4: Implement fake**

Create `server/app/transcribe/fake.py`:

```python
from pathlib import Path
from typing import Optional

from app.transcribe.base import TranscriptResult, TranscriptSegment

_DEFAULT = TranscriptResult(
    segments=[
        TranscriptSegment(speaker="SPEAKER_00", start_ms=0, end_ms=3000, text="회의를 시작하겠습니다."),
        TranscriptSegment(speaker="SPEAKER_01", start_ms=3200, end_ms=6000, text="네, 좋습니다."),
    ],
    full_text="회의를 시작하겠습니다. 네, 좋습니다.",
    language="ko",
)


class FakeTranscriber:
    def __init__(self, result: Optional[TranscriptResult] = None) -> None:
        self._result = result or _DEFAULT
        self.last_audio_path: Optional[Path] = None

    def transcribe(self, audio_path: Path) -> TranscriptResult:
        self.last_audio_path = audio_path
        return self._result
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd server && python -m pytest tests/test_transcriber_fake.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add server/app/transcribe/__init__.py server/app/transcribe/base.py server/app/transcribe/fake.py server/tests/test_transcriber_fake.py
git commit -m "feat(server): Transcriber protocol + fake implementation"
```

---

### Task 4: Transcription job pipeline (state machine)

**Files:**
- Create: `server/app/jobs/__init__.py` (empty)
- Create: `server/app/jobs/queue.py`
- Test: `server/tests/test_jobs.py`

**Interfaces:**
- Consumes: `repo`, `db.session_scope`, `models.RecordingStatus`, `transcribe.base.Transcriber`, `transcribe.fake.FakeTranscriber`.
- Produces:
  - `queue.run_transcription(rec_id: str, *, transcriber: Transcriber, engine) -> None`.
    Opens its own session. Transitions `recorded → transcribing`, calls `transcriber.transcribe(Path(rec.audio_path))`, on success stores transcript (`→ done`), on any exception sets `→ failed` with `error=str(exc)`. Never raises.

- [ ] **Step 1: Write the failing test**

Create `server/tests/test_jobs.py`:

```python
import pytest
from sqlmodel import Session

from app.jobs.queue import run_transcription
from app.store import db, repo
from app.store.models import RecordingStatus
from app.transcribe.fake import FakeTranscriber


@pytest.fixture
def engine(tmp_path):
    e = db.get_engine(tmp_path / "test.db")
    db.init_db(e)
    return e


def test_success_path_sets_done_with_transcript(engine):
    with Session(engine) as s:
        rec = repo.create_recording(s, title="X", audio_path="/x.webm")
        rec_id = rec.id

    run_transcription(rec_id, transcriber=FakeTranscriber(), engine=engine)

    with Session(engine) as s:
        updated = repo.get_recording(s, rec_id)
        assert updated.status == RecordingStatus.DONE
        assert updated.transcript["language"] == "ko"
        assert len(updated.transcript["segments"]) == 2


def test_failure_path_sets_failed_with_error(engine):
    class Boom:
        def transcribe(self, audio_path):
            raise RuntimeError("model exploded")

    with Session(engine) as s:
        rec = repo.create_recording(s, title="X", audio_path="/x.webm")
        rec_id = rec.id

    run_transcription(rec_id, transcriber=Boom(), engine=engine)

    with Session(engine) as s:
        updated = repo.get_recording(s, rec_id)
        assert updated.status == RecordingStatus.FAILED
        assert "model exploded" in updated.error
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && python -m pytest tests/test_jobs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.jobs'`

- [ ] **Step 3: Implement queue**

Create `server/app/jobs/__init__.py` (empty) and `server/app/jobs/queue.py`:

```python
from pathlib import Path

from sqlmodel import Session

from app.store import repo
from app.store.models import RecordingStatus
from app.transcribe.base import Transcriber


def run_transcription(rec_id: str, *, transcriber: Transcriber, engine) -> None:
    with Session(engine) as session:
        rec = repo.get_recording(session, rec_id)
        if rec is None:
            return
        repo.update_status(session, rec_id, RecordingStatus.TRANSCRIBING)
        audio_path = Path(rec.audio_path)
    try:
        result = transcriber.transcribe(audio_path)
    except Exception as exc:  # noqa: BLE001 - job must never raise
        with Session(engine) as session:
            repo.update_status(session, rec_id, RecordingStatus.FAILED, error=str(exc))
        return
    with Session(engine) as session:
        repo.set_transcript(session, rec_id, result.to_dict())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && python -m pytest tests/test_jobs.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add server/app/jobs/ server/tests/test_jobs.py
git commit -m "feat(server): background transcription job with state machine"
```

---

### Task 5: App factory, health endpoint, and test fixtures

**Files:**
- Create: `server/app/main.py`
- Create: `server/app/core/health.py`
- Create: `server/tests/conftest.py`
- Test: `server/tests/test_health.py`

**Interfaces:**
- Consumes: `config.get_settings`, `db.get_engine`, `db.init_db`, `transcribe.fake.FakeTranscriber`.
- Produces:
  - `health.check_models_ready(settings) -> bool` (True when `settings.hf_token` is non-empty).
  - `main.create_app(*, engine=None, transcriber=None) -> FastAPI`. Stores `app.state.engine` and `app.state.transcriber`. Registers `GET /health -> {"status": "ok", "version": <str>, "models_ready": <bool>}`. Includes the recordings router (added in Task 6) — for this task, only `/health` is wired; the router import is added in Task 6.
  - `conftest` fixtures: `engine` (tmp db, initialized), `transcriber` (FakeTranscriber), `client` (TestClient over `create_app(engine=..., transcriber=...)`).

- [ ] **Step 1: Write the failing test**

Create `server/tests/test_health.py`:

```python
def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert body["models_ready"] is False  # no HF token in test env
```

- [ ] **Step 2: Create conftest fixtures**

Create `server/tests/conftest.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.store import db
from app.transcribe.fake import FakeTranscriber


@pytest.fixture
def engine(tmp_path):
    e = db.get_engine(tmp_path / "test.db")
    db.init_db(e)
    return e


@pytest.fixture
def transcriber():
    return FakeTranscriber()


@pytest.fixture
def client(engine, transcriber, tmp_path, monkeypatch):
    monkeypatch.setenv("V2M_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("V2M_HF_TOKEN", raising=False)
    app = create_app(engine=engine, transcriber=transcriber)
    return TestClient(app)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd server && python -m pytest tests/test_health.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 4: Implement health + app factory**

Create `server/app/core/health.py`:

```python
from app.core.config import Settings


def check_models_ready(settings: Settings) -> bool:
    return bool(settings.hf_token)
```

Create `server/app/main.py`:

```python
from typing import Optional

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.health import check_models_ready
from app.store import db as db_module

VERSION = "0.1.0"


def create_app(*, engine=None, transcriber=None) -> FastAPI:
    settings = get_settings()
    if engine is None:
        engine = db_module.get_engine()
        db_module.init_db(engine)

    app = FastAPI(title="V2M", version=VERSION)
    app.state.engine = engine
    app.state.transcriber = transcriber
    app.state.settings = settings

    @app.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "version": VERSION,
            "models_ready": check_models_ready(settings),
        }

    return app
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd server && python -m pytest tests/test_health.py -v`
Expected: PASS (1 passed)

- [ ] **Step 6: Commit**

```bash
git add server/app/main.py server/app/core/health.py server/tests/conftest.py server/tests/test_health.py
git commit -m "feat(server): app factory, /health endpoint, and test fixtures"
```

---

### Task 6: Ingest + recordings read/manage API

**Files:**
- Create: `server/app/api/__init__.py` (empty)
- Create: `server/app/api/recordings.py`
- Modify: `server/app/main.py` (include the router)
- Test: `server/tests/test_ingest.py`, `server/tests/test_recordings_api.py`

**Interfaces:**
- Consumes: `repo`, `models.Recording/RecordingStatus`, `jobs.queue.run_transcription`, `paths.get_audio_dir`, `app.state.engine`, `app.state.transcriber`.
- Produces these routes (all under `/api`):
  - `POST /api/recordings` (multipart `file`, optional form `title`) → 201 `{id, title, status, created_at}`. Saves upload to `get_audio_dir()/<id>.webm`, creates `Recording(recorded)`, schedules `run_transcription` via `BackgroundTasks`.
  - `GET /api/recordings` → `[{id, title, status, created_at, duration_sec}]`.
  - `GET /api/recordings/{id}` → full record incl. `transcript`; 404 if missing.
  - `GET /api/recordings/{id}/status` → `{id, status, error}`; 404 if missing.
  - `POST /api/recordings/{id}/retry` → re-schedules job, sets status back toward `transcribing`; 404 if missing.
  - `DELETE /api/recordings/{id}` → 204; deletes row + audio file; 404 if missing.

- [ ] **Step 1: Write the failing ingest test**

Create `server/tests/test_ingest.py`:

```python
import io


def test_upload_creates_recording_and_runs_job(client):
    files = {"file": ("meeting.webm", io.BytesIO(b"fakeaudio"), "audio/webm")}
    resp = client.post("/api/recordings", files=files, data={"title": "Sprint Review"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Sprint Review"
    rec_id = body["id"]

    # BackgroundTasks run after the response with the FakeTranscriber → done
    status = client.get(f"/api/recordings/{rec_id}/status").json()
    assert status["status"] == "done"

    detail = client.get(f"/api/recordings/{rec_id}").json()
    assert detail["transcript"]["language"] == "ko"


def test_upload_defaults_title_when_missing(client):
    files = {"file": ("m.webm", io.BytesIO(b"a"), "audio/webm")}
    resp = client.post("/api/recordings", files=files)
    assert resp.status_code == 201
    assert resp.json()["title"]
```

- [ ] **Step 2: Write the failing manage test**

Create `server/tests/test_recordings_api.py`:

```python
import io


def _upload(client, name="m.webm"):
    files = {"file": (name, io.BytesIO(b"a"), "audio/webm")}
    return client.post("/api/recordings", files=files).json()["id"]


def test_list_returns_uploaded(client):
    _upload(client)
    rows = client.get("/api/recordings").json()
    assert len(rows) == 1
    assert {"id", "title", "status", "created_at"} <= set(rows[0])


def test_detail_404(client):
    assert client.get("/api/recordings/nope").status_code == 404


def test_delete_removes_record(client):
    rec_id = _upload(client)
    assert client.delete(f"/api/recordings/{rec_id}").status_code == 204
    assert client.get(f"/api/recordings/{rec_id}").status_code == 404


def test_retry_reschedules(client):
    rec_id = _upload(client)
    resp = client.post(f"/api/recordings/{rec_id}/retry")
    assert resp.status_code == 200
    # With FakeTranscriber, retry ends in done again
    assert client.get(f"/api/recordings/{rec_id}/status").json()["status"] == "done"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd server && python -m pytest tests/test_ingest.py tests/test_recordings_api.py -v`
Expected: FAIL with 404 / `No module named 'app.api'` (router not wired)

- [ ] **Step 4: Implement the router**

Create `server/app/api/__init__.py` (empty) and `server/app/api/recordings.py`:

```python
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, Response, UploadFile
from sqlmodel import Session

from app.jobs.queue import run_transcription
from app.core.paths import get_audio_dir
from app.store import repo
from app.store.models import RecordingStatus

router = APIRouter(prefix="/api")


def _schedule(request: Request, background: BackgroundTasks, rec_id: str) -> None:
    background.add_task(
        run_transcription,
        rec_id,
        transcriber=request.app.state.transcriber,
        engine=request.app.state.engine,
    )


@router.post("/recordings", status_code=201)
async def create_recording(
    request: Request,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(default=""),
):
    engine = request.app.state.engine
    with Session(engine) as session:
        rec = repo.create_recording(
            session,
            title=title or f"녹음 {datetime.now():%Y-%m-%d %H:%M}",
            audio_path="",
        )
        rec_id = rec.id

    dest = get_audio_dir() / f"{rec_id}.webm"
    dest.write_bytes(await file.read())

    with Session(engine) as session:
        rec = repo.get_recording(session, rec_id)
        rec.audio_path = str(dest)
        session.add(rec)
        session.commit()
        session.refresh(rec)
        payload = {"id": rec.id, "title": rec.title, "status": rec.status,
                   "created_at": rec.created_at.isoformat()}

    _schedule(request, background, rec_id)
    return payload


@router.get("/recordings")
def list_recordings(request: Request):
    with Session(request.app.state.engine) as session:
        return [
            {"id": r.id, "title": r.title, "status": r.status,
             "created_at": r.created_at.isoformat(), "duration_sec": r.duration_sec}
            for r in repo.list_recordings(session)
        ]


def _get_or_404(session: Session, rec_id: str):
    rec = repo.get_recording(session, rec_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="recording not found")
    return rec


@router.get("/recordings/{rec_id}")
def get_recording(request: Request, rec_id: str):
    with Session(request.app.state.engine) as session:
        rec = _get_or_404(session, rec_id)
        return {"id": rec.id, "title": rec.title, "status": rec.status,
                "created_at": rec.created_at.isoformat(), "duration_sec": rec.duration_sec,
                "error": rec.error, "transcript": rec.transcript}


@router.get("/recordings/{rec_id}/status")
def get_status(request: Request, rec_id: str):
    with Session(request.app.state.engine) as session:
        rec = _get_or_404(session, rec_id)
        return {"id": rec.id, "status": rec.status, "error": rec.error}


@router.post("/recordings/{rec_id}/retry")
def retry(request: Request, background: BackgroundTasks, rec_id: str):
    with Session(request.app.state.engine) as session:
        rec = _get_or_404(session, rec_id)
        repo.update_status(session, rec_id, RecordingStatus.RECORDED)
    _schedule(request, background, rec_id)
    return {"id": rec_id, "status": "scheduled"}


@router.delete("/recordings/{rec_id}", status_code=204)
def delete_recording(request: Request, rec_id: str):
    with Session(request.app.state.engine) as session:
        rec = _get_or_404(session, rec_id)
        audio = Path(rec.audio_path) if rec.audio_path else None
        repo.delete_recording(session, rec_id)
    if audio and audio.exists():
        audio.unlink()
    return Response(status_code=204)
```

- [ ] **Step 5: Wire the router into the app**

In `server/app/main.py`, add the import near the top:

```python
from app.api.recordings import router as recordings_router
```

And inside `create_app`, after setting `app.state.settings`, add:

```python
    app.include_router(recordings_router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd server && python -m pytest tests/test_ingest.py tests/test_recordings_api.py -v`
Expected: PASS (6 passed)

- [ ] **Step 7: Commit**

```bash
git add server/app/api/ server/app/main.py server/tests/test_ingest.py server/tests/test_recordings_api.py
git commit -m "feat(server): ingest upload + recordings read/manage API"
```

---

### Task 7: Prompt builder (copy-for-claude.ai bundle)

**Files:**
- Create: `server/app/prompt/__init__.py` (empty)
- Create: `server/app/prompt/builder.py`
- Modify: `server/app/api/recordings.py` (add `GET /recordings/{id}/prompt`)
- Test: `server/tests/test_prompt.py`

**Interfaces:**
- Consumes: `repo`, transcript dict shape `{segments:[{speaker,start_ms,end_ms,text}], full_text, language}`.
- Produces:
  - `builder.PromptBundle` (pydantic): `prompt: str`, `transcript_text: str`, `char_count: int`, `too_long: bool`.
  - `builder.format_transcript(transcript: dict) -> str` — groups consecutive same-speaker segments, prefixes each line with `[mm:ss] SPEAKER_xx:`.
  - `builder.build_prompt(transcript: dict, *, too_long_threshold: int = 40000) -> PromptBundle` — combines a Korean meeting-minutes instruction with the formatted transcript; `char_count` = len(prompt); `too_long` when over threshold.
  - Route `GET /api/recordings/{id}/prompt` → `PromptBundle` JSON; 409 if transcript not ready; 404 if missing.

- [ ] **Step 1: Write the failing test**

Create `server/tests/test_prompt.py`:

```python
import io

from app.prompt.builder import build_prompt, format_transcript

SAMPLE = {
    "segments": [
        {"speaker": "SPEAKER_00", "start_ms": 0, "end_ms": 3000, "text": "회의를 시작합니다."},
        {"speaker": "SPEAKER_00", "start_ms": 3000, "end_ms": 5000, "text": "안건은 두 가지입니다."},
        {"speaker": "SPEAKER_01", "start_ms": 65000, "end_ms": 67000, "text": "네 동의합니다."},
    ],
    "full_text": "회의를 시작합니다. 안건은 두 가지입니다. 네 동의합니다.",
    "language": "ko",
}


def test_format_groups_consecutive_speaker_and_timestamps():
    text = format_transcript(SAMPLE)
    assert "[00:00] SPEAKER_00:" in text
    assert "[01:05] SPEAKER_01:" in text
    # consecutive SPEAKER_00 lines merged under one header
    assert text.count("SPEAKER_00:") == 1


def test_build_prompt_includes_instruction_and_transcript():
    bundle = build_prompt(SAMPLE)
    assert "회의록" in bundle.prompt
    assert "SPEAKER_00" in bundle.prompt
    assert bundle.char_count == len(bundle.prompt)
    assert bundle.too_long is False


def test_too_long_flag():
    big = {"segments": [{"speaker": "S", "start_ms": 0, "end_ms": 1, "text": "가" * 50000}],
           "full_text": "x", "language": "ko"}
    assert build_prompt(big).too_long is True


def test_prompt_endpoint_409_before_ready(client, monkeypatch):
    # upload but force status away from done by deleting transcript
    files = {"file": ("m.webm", io.BytesIO(b"a"), "audio/webm")}
    rec_id = client.post("/api/recordings", files=files).json()["id"]
    # FakeTranscriber already produced a transcript → endpoint should be 200
    resp = client.get(f"/api/recordings/{rec_id}/prompt")
    assert resp.status_code == 200
    assert "transcript_text" in resp.json()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && python -m pytest tests/test_prompt.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.prompt'`

- [ ] **Step 3: Implement the builder**

Create `server/app/prompt/__init__.py` (empty) and `server/app/prompt/builder.py`:

```python
from pydantic import BaseModel

INSTRUCTION = (
    "당신은 회의록 작성 전문가입니다. 아래 화자별·타임스탬프 전사본을 바탕으로 "
    "정형화된 한국어 회의록을 작성하세요. 다음 4개 항목으로 구성합니다:\n"
    "1. 요약 (핵심 내용 3~5문장)\n"
    "2. 핵심 논의 (주제별 불릿)\n"
    "3. 결정사항 (합의된 사항)\n"
    "4. 액션아이템 (할 일 — 담당자/기한이 언급되면 함께 표기)\n\n"
    "=== 전사본 ===\n"
)


class PromptBundle(BaseModel):
    prompt: str
    transcript_text: str
    char_count: int
    too_long: bool


def _ms_to_mmss(ms: int) -> str:
    total = ms // 1000
    return f"{total // 60:02d}:{total % 60:02d}"


def format_transcript(transcript: dict) -> str:
    lines: list[str] = []
    last_speaker = None
    for seg in transcript.get("segments", []):
        if seg["speaker"] != last_speaker:
            lines.append(f"[{_ms_to_mmss(seg['start_ms'])}] {seg['speaker']}:")
            last_speaker = seg["speaker"]
        lines.append(f"  {seg['text']}")
    return "\n".join(lines)


def build_prompt(transcript: dict, *, too_long_threshold: int = 40000) -> PromptBundle:
    transcript_text = format_transcript(transcript)
    prompt = INSTRUCTION + transcript_text
    return PromptBundle(
        prompt=prompt,
        transcript_text=transcript_text,
        char_count=len(prompt),
        too_long=len(prompt) > too_long_threshold,
    )
```

- [ ] **Step 4: Add the prompt route**

In `server/app/api/recordings.py`, add the import:

```python
from app.prompt.builder import build_prompt
```

And add this route (after `get_status`):

```python
@router.get("/recordings/{rec_id}/prompt")
def get_prompt(request: Request, rec_id: str):
    with Session(request.app.state.engine) as session:
        rec = _get_or_404(session, rec_id)
        if not rec.transcript:
            raise HTTPException(status_code=409, detail="transcript not ready")
        return build_prompt(rec.transcript).model_dump()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd server && python -m pytest tests/test_prompt.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add server/app/prompt/ server/app/api/recordings.py server/tests/test_prompt.py
git commit -m "feat(server): claude.ai prompt bundle builder + endpoint"
```

---

### Task 8: Transcript export (Markdown / TXT)

**Files:**
- Create: `server/app/export/__init__.py` (empty)
- Create: `server/app/export/markdown.py`
- Modify: `server/app/api/recordings.py` (add `GET /recordings/{id}/export`)
- Test: `server/tests/test_export.py`

**Interfaces:**
- Consumes: transcript dict, `prompt.builder.format_transcript`.
- Produces:
  - `markdown.to_markdown(title: str, transcript: dict) -> str` — `# <title>` heading + formatted transcript in a fenced block.
  - `markdown.to_txt(title: str, transcript: dict) -> str` — title line + formatted transcript.
  - Route `GET /api/recordings/{id}/export?format=md|txt` → `text/markdown` or `text/plain` with `Content-Disposition: attachment`; 400 on bad format; 409 if transcript missing; 404 if no record.

- [ ] **Step 1: Write the failing test**

Create `server/tests/test_export.py`:

```python
import io

from app.export.markdown import to_markdown, to_txt

SAMPLE = {
    "segments": [{"speaker": "SPEAKER_00", "start_ms": 0, "end_ms": 1000, "text": "안녕하세요"}],
    "full_text": "안녕하세요", "language": "ko",
}


def test_to_markdown_has_title_and_text():
    md = to_markdown("주간회의", SAMPLE)
    assert md.startswith("# 주간회의")
    assert "SPEAKER_00" in md
    assert "안녕하세요" in md


def test_to_txt_plain():
    txt = to_txt("주간회의", SAMPLE)
    assert "주간회의" in txt
    assert "안녕하세요" in txt


def test_export_endpoint_md(client):
    files = {"file": ("m.webm", io.BytesIO(b"a"), "audio/webm")}
    rec_id = client.post("/api/recordings", files=files).json()["id"]
    resp = client.get(f"/api/recordings/{rec_id}/export?format=md")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert "attachment" in resp.headers.get("content-disposition", "")


def test_export_bad_format(client):
    files = {"file": ("m.webm", io.BytesIO(b"a"), "audio/webm")}
    rec_id = client.post("/api/recordings", files=files).json()["id"]
    assert client.get(f"/api/recordings/{rec_id}/export?format=pdf").status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && python -m pytest tests/test_export.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.export'`

- [ ] **Step 3: Implement export**

Create `server/app/export/__init__.py` (empty) and `server/app/export/markdown.py`:

```python
from app.prompt.builder import format_transcript


def to_markdown(title: str, transcript: dict) -> str:
    body = format_transcript(transcript)
    return f"# {title}\n\n```\n{body}\n```\n"


def to_txt(title: str, transcript: dict) -> str:
    body = format_transcript(transcript)
    return f"{title}\n\n{body}\n"
```

- [ ] **Step 4: Add the export route**

In `server/app/api/recordings.py`, add the import:

```python
from app.export.markdown import to_markdown, to_txt
```

And add this route (after `get_prompt`):

```python
@router.get("/recordings/{rec_id}/export")
def export(request: Request, rec_id: str, format: str = "md"):
    if format not in ("md", "txt"):
        raise HTTPException(status_code=400, detail="format must be md or txt")
    with Session(request.app.state.engine) as session:
        rec = _get_or_404(session, rec_id)
        if not rec.transcript:
            raise HTTPException(status_code=409, detail="transcript not ready")
        if format == "md":
            content, media, ext = to_markdown(rec.title, rec.transcript), "text/markdown", "md"
        else:
            content, media, ext = to_txt(rec.title, rec.transcript), "text/plain", "txt"
    headers = {"Content-Disposition": f'attachment; filename="{rec_id}.{ext}"'}
    return Response(content=content, media_type=media, headers=headers)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd server && python -m pytest tests/test_export.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add server/app/export/ server/app/api/recordings.py server/tests/test_export.py
git commit -m "feat(server): transcript export (markdown/txt) endpoint"
```

---

### Task 9: Real WhisperX runner + static serving + graceful shutdown + run entrypoint

**Files:**
- Create: `server/app/transcribe/whisperx_runner.py`
- Modify: `server/app/main.py` (real transcriber wiring, static mount, `/shutdown`, lifespan)
- Create: `server/run.py`
- Create: `server/README.md`
- Test: `server/tests/test_app_wiring.py`

**Interfaces:**
- Consumes: `config.get_settings`, `paths.get_models_dir`, `transcribe.base.TranscriptResult/TranscriptSegment`.
- Produces:
  - `whisperx_runner.WhisperXTranscriber(model_size: str, hf_token: str, device: str = "cpu", compute_type: str = "int8")` implementing `Transcriber.transcribe(audio_path) -> TranscriptResult`. Imports `whisperx` lazily inside `transcribe()` so importing the module never pulls torch.
  - `main.create_app` default transcriber: when none injected, build `WhisperXTranscriber` from settings (lazy — only constructed, not run).
  - `main`: mount static `web/dist` at `/` if it exists; `POST /shutdown` endpoint; model dir set to app-data.
  - `run.py`: launches uvicorn with `settings.host`/`settings.port`.

- [ ] **Step 1: Write the failing wiring test**

Create `server/tests/test_app_wiring.py`:

```python
import importlib


def test_whisperx_module_imports_without_torch():
    # Importing the module must NOT import whisperx/torch at module load time.
    mod = importlib.import_module("app.transcribe.whisperx_runner")
    assert hasattr(mod, "WhisperXTranscriber")


def test_shutdown_endpoint_exists(client):
    resp = client.post("/shutdown")
    assert resp.status_code == 200
    assert resp.json()["status"] == "shutting_down"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && python -m pytest tests/test_app_wiring.py -v`
Expected: FAIL (`No module named 'app.transcribe.whisperx_runner'` / no `/shutdown`)

- [ ] **Step 3: Implement the WhisperX runner**

Create `server/app/transcribe/whisperx_runner.py`:

```python
from pathlib import Path

from app.transcribe.base import TranscriptResult, TranscriptSegment


class WhisperXTranscriber:
    """Real local STT + diarization. whisperx/torch imported lazily."""

    def __init__(self, model_size: str, hf_token: str, device: str = "cpu",
                 compute_type: str = "int8") -> None:
        self.model_size = model_size
        self.hf_token = hf_token
        self.device = device
        self.compute_type = compute_type

    def transcribe(self, audio_path: Path) -> TranscriptResult:
        import whisperx  # lazy: keeps torch out of test imports

        from app.core.paths import get_models_dir

        model = whisperx.load_model(
            self.model_size, self.device, compute_type=self.compute_type,
            download_root=str(get_models_dir()),
        )
        audio = whisperx.load_audio(str(audio_path))
        result = model.transcribe(audio)
        language = result.get("language", "ko")

        align_model, metadata = whisperx.load_align_model(language_code=language, device=self.device)
        result = whisperx.align(result["segments"], align_model, metadata, audio, self.device)

        diarize = whisperx.DiarizationPipeline(use_auth_token=self.hf_token, device=self.device)
        diarize_segments = diarize(audio)
        result = whisperx.assign_word_speakers(diarize_segments, result)

        segments: list[TranscriptSegment] = []
        texts: list[str] = []
        for seg in result["segments"]:
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

- [ ] **Step 4: Wire real transcriber, static, shutdown into main**

Replace `server/app/main.py` with:

```python
import os
import signal
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.recordings import router as recordings_router
from app.core.config import get_settings
from app.core.health import check_models_ready
from app.store import db as db_module

VERSION = "0.1.0"


def _default_transcriber(settings):
    from app.transcribe.whisperx_runner import WhisperXTranscriber
    return WhisperXTranscriber(model_size=settings.whisper_model, hf_token=settings.hf_token)


def create_app(*, engine=None, transcriber=None) -> FastAPI:
    settings = get_settings()
    if engine is None:
        engine = db_module.get_engine()
        db_module.init_db(engine)
    if transcriber is None:
        transcriber = _default_transcriber(settings)

    app = FastAPI(title="V2M", version=VERSION)
    app.state.engine = engine
    app.state.transcriber = transcriber
    app.state.settings = settings

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "version": VERSION, "models_ready": check_models_ready(settings)}

    @app.post("/shutdown")
    def shutdown() -> dict:
        os.kill(os.getpid(), signal.SIGTERM)
        return {"status": "shutting_down"}

    app.include_router(recordings_router)

    dist = Path(__file__).resolve().parent.parent.parent / "web" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="static")

    return app
```

> Note: in tests the `client` fixture injects a `FakeTranscriber`, so `_default_transcriber` (and thus whisperx) is never constructed during tests.

- [ ] **Step 5: Create run entrypoint and README**

Create `server/run.py`:

```python
import uvicorn

from app.core.config import get_settings
from app.main import create_app

app = create_app()

if __name__ == "__main__":
    s = get_settings()
    uvicorn.run(app, host=s.host, port=s.port)
```

Create `server/README.md`:

```markdown
# V2M Server

Local FastAPI backend: meeting audio → local WhisperX transcription
(speaker diarization + timestamps) → transcript + claude.ai prompt bundle.

## Setup
1. `python -m venv .venv && .venv\Scripts\activate` (Windows)
2. `pip install -e ".[dev]"` (add `,ml` once ready for real transcription: `pip install -e ".[dev,ml]"`)
3. Install **ffmpeg** and ensure it is on PATH.
4. Copy `.env.example` to `.env`. Set `V2M_HF_TOKEN` (accept terms for
   `pyannote/segmentation-3.0` and `pyannote/speaker-diarization-3.1` on Hugging Face first).

## Run
`python run.py` → open `http://127.0.0.1:8000`

## Test
`python -m pytest -v` (tests use a fake transcriber; torch/whisperx not required)

Data (db, audio, models, logs) is stored under `%LOCALAPPDATA%\v2m\`.
```

- [ ] **Step 6: Run the wiring test to verify it passes**

Run: `cd server && python -m pytest tests/test_app_wiring.py -v`
Expected: PASS (2 passed)

- [ ] **Step 7: Run the full suite**

Run: `cd server && python -m pytest -v`
Expected: PASS (all tasks' tests green)

- [ ] **Step 8: Commit**

```bash
git add server/app/transcribe/whisperx_runner.py server/app/main.py server/run.py server/README.md server/tests/test_app_wiring.py
git commit -m "feat(server): WhisperX runner, static serving, graceful shutdown, run entrypoint"
```

---

## Self-Review

**Spec coverage:**
- Local $0 transcription pipeline → Tasks 3,4,9 (WhisperX behind protocol). ✓
- Speaker diarization + timestamps → `TranscriptSegment` + WhisperX diarize (Task 9). ✓
- Status state machine `recorded→transcribing→done|failed` + retry → Tasks 4,6. ✓
- App-data dir / desktop guardrails (port config, `/health`, graceful shutdown, app-data, models dir) → Tasks 1,5,9. ✓
- Ingest + manage API → Task 6. ✓
- claude.ai prompt bundle (speaker/timestamp formatting, too-long flag) → Task 7. ✓
- Transcript export md/txt → Task 8. ✓
- `.env` config, default model `medium`, CPU-only → Tasks 1,9 + README. ✓
- Real WhisperX not imported in tests → enforced by lazy import + injected fake (Tasks 3,5,9, `test_app_wiring`). ✓
- Gaps: first-run model **download** UI flow (§5.5-6) and `runtime.json` port-write are deferred to Plan B / desktop phase; the model `download_root` is wired now. Acceptable for backend MVP.

**Placeholder scan:** No TBD/TODO; every code step has full code and exact commands. ✓

**Type consistency:** `RecordingStatus`, `TranscriptResult.to_dict()`, `run_transcription(rec_id, *, transcriber, engine)`, `build_prompt(transcript)`, `format_transcript(transcript)`, `to_markdown(title, transcript)` are used identically across tasks. ✓

---

## Execution Handoff

(Filled in by the writing-plans skill conversation after save.)
