# V2M Frontend + Meeting-Meta Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the confirmed dark-modern V2M UI — a Vite + React + TypeScript SPA that records meeting audio, captures meeting metadata, uploads to the local backend, shows the speaker-labeled timestamped transcript, and copies a `회의 정보 + 전사본 + 지시문` bundle to the clipboard for pasting into the claude.ai desktop app — plus the backend extension that stores and emits that metadata.

**Architecture:** Two phases. **Phase A** extends the existing FastAPI backend with an optional `Recording.meta` JSON column, accepts it on `POST`, adds a `PATCH` endpoint, and threads it into the prompt/export builders (all backward-compatible). **Phase B** builds a small SPA (no router — view state is `'home' | {detailId}`). A typed `lib/api.ts` wraps the `/api` contract; a `useRecorder` hook captures `webm/opus` via `MediaRecorder`; a shared `MeetingForm` drives both create (home) and edit (detail); `CopyForClaude` copies-only (no auto-open). Styling is the design-system tokens ported to CSS variables.

**Tech Stack:** Backend: FastAPI + SQLModel + pytest (no torch). Frontend: Vite 5, React 18, TypeScript 5 (strict), Vitest 2 + @testing-library/react (jsdom). No router/state libraries (YAGNI).

**Spec:** [docs/superpowers/specs/v2m-frontend-design.md](../specs/v2m-frontend-design.md) · **Design system:** [.superdesign/design-system.md](../../../.superdesign/design-system.md)

## Global Constraints

- **Backward compatibility:** `meta` is fully optional everywhere; the existing 39-test backend suite must stay green. No module-level `import whisperx`/`import torch` (the test-without-ML invariant).
- **Backend run:** from `server/`, use `.venv/Scripts/python.exe -m pytest -q`. Tests use `FakeTranscriber`; never require torch.
- Frontend: Vite + React + TypeScript only, `strict: true`. No router/state libraries.
- App calls **relative `/api/...`** and `/health` — never an absolute host. Dev: Vite proxy to `http://127.0.0.1:8000`. Prod: same-origin (FastAPI serves `web/dist`).
- `RecordingStatus` values are exactly `recorded | transcribing | done | failed`.
- **No in-app LLM / no minutes storage.** **No auto-opening claude.ai** — `CopyForClaude` writes the clipboard and shows a toast only.
- Single font only (Pretendard stack); **no monospace font**; numbers use `font-variant-numeric: tabular-nums`. Single indigo/violet accent; status colors are the defined 4 only. All UI copy is Korean.
- Audio capture: `audio/webm;codecs=opus` when `MediaRecorder.isTypeSupported`; upload filename `recording.webm`, multipart field `file`.
- Build output dir is `web/dist` (backend mounts it at `/`).
- `meta` shape (all fields optional strings): `{ date, time, location, attendees, agenda }`.
- TDD: failing test first, minimal implementation, frequent commits. DRY, YAGNI.

### Backend API contract after Phase A (what Phase B consumes)
- `GET /api/recordings` → `{id,title,status,created_at,duration_sec,meta}[]`
- `POST /api/recordings` (multipart `file`, optional `title`, optional `meta` = JSON string) → `201 {id,title,status,created_at,meta}`
- `PATCH /api/recordings/{id}` (JSON `{title?, meta?}`) → `200 {id,title,status,created_at,duration_sec,error,transcript,meta}`
- `GET /api/recordings/{id}` → `{...,transcript,meta}`
- `GET /api/recordings/{id}/status` → `{id,status,error}`
- `POST /api/recordings/{id}/retry` → `200`
- `DELETE /api/recordings/{id}` → `204`
- `GET /api/recordings/{id}/prompt` → `{prompt,transcript_text,char_count,too_long}` (prompt includes the `회의 정보` block when meta present)
- `GET /api/recordings/{id}/export?format=md|txt` → file download (includes meta block)

---

# Phase A — Backend meeting-meta extension

All paths below are relative to `server/`. Run tests with `.venv/Scripts/python.exe -m pytest -q`.

### Task A1: `Recording.meta` column + repo update helper

**Files:**
- Modify: `app/store/models.py`
- Modify: `app/store/repo.py`
- Test: `tests/test_repo.py`

**Interfaces:**
- Produces:
  - `Recording.meta: Optional[dict]` (JSON column, default `None`).
  - `repo.update_recording(session, rec_id, *, title: Optional[str] = None, meta: Optional[dict] = None) -> Recording` — partial update; only non-`None` args are applied; raises `ValueError` for missing id; returns the refreshed row.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_repo.py`:

```python
def test_meta_defaults_none_and_roundtrips(engine):
    with Session(engine) as s:
        rec = repo.create_recording(s, title="X", audio_path="/x")
        assert rec.meta is None
        updated = repo.update_recording(
            s, rec.id, meta={"location": "회의실 A", "attendees": "홍길동, 김철수"}
        )
        assert updated.meta["location"] == "회의실 A"
        assert repo.get_recording(s, rec.id).meta["attendees"] == "홍길동, 김철수"


def test_update_recording_title_only_keeps_meta(engine):
    with Session(engine) as s:
        rec = repo.create_recording(s, title="X", audio_path="/x")
        repo.update_recording(s, rec.id, meta={"agenda": "Q3"})
        repo.update_recording(s, rec.id, title="새 제목")
        got = repo.get_recording(s, rec.id)
        assert got.title == "새 제목"
        assert got.meta == {"agenda": "Q3"}


def test_update_recording_missing_id_raises(engine):
    with Session(engine) as s:
        with pytest.raises(ValueError):
            repo.update_recording(s, "missing", title="x")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_repo.py -q`
Expected: FAIL — `Recording` has no `meta`; `repo.update_recording` not defined.

- [ ] **Step 3: Add the `meta` column**

In `app/store/models.py`, add to `Recording` (after `transcript`):

```python
    meta: Optional[dict] = Field(default=None, sa_column=Column(JSON))
```

- [ ] **Step 4: Add the repo helper**

In `app/store/repo.py`, add:

```python
def update_recording(session: Session, rec_id: str, *, title: Optional[str] = None,
                     meta: Optional[dict] = None) -> Recording:
    rec = session.get(Recording, rec_id)
    if rec is None:
        raise ValueError(f"recording not found: {rec_id}")
    if title is not None:
        rec.title = title
    if meta is not None:
        rec.meta = meta
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_repo.py -q`
Expected: PASS (existing repo tests + 3 new).

- [ ] **Step 6: Commit**

```bash
git add app/store/models.py app/store/repo.py tests/test_repo.py
git commit -m "feat(server): add optional Recording.meta + update_recording helper"
```

---

### Task A2: `POST`/`GET`/list carry `meta`

**Files:**
- Modify: `app/api/recordings.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `repo.update_recording`.
- Produces: `POST /api/recordings` accepts optional form field `meta` (JSON string), parses it to a dict, and stores it; `GET /api/recordings/{id}` and `GET /api/recordings` responses include `meta`.

> Note: check the existing `tests/` for the API test filename. If the suite uses `tests/test_api.py` with a `client` fixture (from `tests/conftest.py`), append there. If API tests live in another file (e.g. `test_recordings_api.py`), append to that file instead. The fixture is `client` (a `TestClient`).

- [ ] **Step 1: Write the failing test**

Append to the API test file (uses the existing `client` fixture):

```python
import io
import json


def _upload(client, *, title="회의", meta=None):
    files = {"file": ("recording.webm", io.BytesIO(b"audio-bytes"), "audio/webm")}
    data = {"title": title}
    if meta is not None:
        data["meta"] = json.dumps(meta, ensure_ascii=False)
    return client.post("/api/recordings", files=files, data=data)


def test_post_stores_and_returns_meta(client):
    meta = {"location": "회의실 A", "attendees": "홍길동", "agenda": "킥오프"}
    r = _upload(client, meta=meta)
    assert r.status_code == 201
    rec_id = r.json()["id"]
    assert r.json()["meta"] == meta
    got = client.get(f"/api/recordings/{rec_id}").json()
    assert got["meta"]["location"] == "회의실 A"


def test_post_without_meta_is_null(client):
    r = _upload(client)
    assert r.status_code == 201
    assert r.json()["meta"] is None


def test_list_includes_meta(client):
    _upload(client, meta={"agenda": "X"})
    rows = client.get("/api/recordings").json()
    assert rows[0]["meta"] == {"agenda": "X"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api.py -q` (adjust filename if different)
Expected: FAIL — response has no `meta` key.

- [ ] **Step 3: Implement meta on POST + responses**

In `app/api/recordings.py`, add `import json` at top. Change `create_recording`'s signature to accept meta and parse it:

```python
@router.post("/recordings", status_code=201)
async def create_recording(
    request: Request,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(default=""),
    meta: str = Form(default=""),
):
    parsed_meta = json.loads(meta) if meta else None
    engine = request.app.state.engine
    with Session(engine) as session:
        rec = repo.create_recording(
            session,
            title=title or f"녹음 {datetime.now():%Y-%m-%d %H:%M}",
            audio_path="",
        )
        rec_id = rec.id
        if parsed_meta is not None:
            repo.update_recording(session, rec_id, meta=parsed_meta)
```

Keep the audio-save block as-is. Then update the returned `payload` and the read endpoints to include `meta`:

```python
        payload = {"id": rec.id, "title": rec.title, "status": rec.status,
                   "created_at": rec.created_at.isoformat(), "meta": rec.meta}
```

In `list_recordings`, add `"meta": r.meta` to each dict. In `get_recording`, add `"meta": rec.meta` to the returned dict.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api.py -q`
Expected: PASS (existing API tests + 3 new).

- [ ] **Step 5: Commit**

```bash
git add app/api/recordings.py tests/test_api.py
git commit -m "feat(server): accept and return Recording.meta on create/get/list"
```

---

### Task A3: `PATCH /api/recordings/{id}`

**Files:**
- Modify: `app/api/recordings.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `repo.update_recording`, `_get_or_404`.
- Produces: `PATCH /api/recordings/{id}` with JSON body `{title?, meta?}` → updated full detail dict (same shape as `GET /api/recordings/{id}`); 404 for unknown id.

- [ ] **Step 1: Write the failing test**

Append to the API test file:

```python
def test_patch_updates_meta_and_title(client):
    rec_id = _upload(client, title="원본").json()["id"]
    r = client.patch(f"/api/recordings/{rec_id}",
                      json={"title": "수정본", "meta": {"location": "B룸"}})
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "수정본"
    assert body["meta"]["location"] == "B룸"
    assert "transcript" in body  # full detail shape


def test_patch_unknown_id_404(client):
    r = client.patch("/api/recordings/missing", json={"title": "x"})
    assert r.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api.py -q`
Expected: FAIL — 405/404 (no PATCH route).

- [ ] **Step 3: Implement the PATCH route**

In `app/api/recordings.py`, add a Pydantic body model near the top (after imports) and the route (place it after `get_recording`):

```python
from pydantic import BaseModel


class RecordingPatch(BaseModel):
    title: str | None = None
    meta: dict | None = None


@router.patch("/recordings/{rec_id}")
def patch_recording(request: Request, rec_id: str, body: RecordingPatch):
    with Session(request.app.state.engine) as session:
        _get_or_404(session, rec_id)
        rec = repo.update_recording(session, rec_id, title=body.title, meta=body.meta)
        return {"id": rec.id, "title": rec.title, "status": rec.status,
                "created_at": rec.created_at.isoformat(), "duration_sec": rec.duration_sec,
                "error": rec.error, "transcript": rec.transcript, "meta": rec.meta}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/recordings.py tests/test_api.py
git commit -m "feat(server): PATCH /api/recordings/{id} for title+meta edits"
```

---

### Task A4: `meta` block in prompt + export

**Files:**
- Modify: `app/prompt/builder.py`
- Modify: `app/export/markdown.py`
- Modify: `app/api/recordings.py` (pass `meta` into `build_prompt`)
- Test: `tests/test_prompt.py`, `tests/test_export.py`

**Interfaces:**
- Produces:
  - `format_meta(meta: Optional[dict]) -> str` — Korean `=== 회의 정보 ===` block; empty string when meta is falsy or has no non-empty fields; omits empty fields; merges `date`+`time` onto one `일자` line.
  - `build_prompt(transcript, meta=None, *, too_long_threshold=40000) -> PromptBundle` — inserts the meta block between INSTRUCTION and the transcript; `char_count`/`too_long` computed on the full text.
  - `to_markdown(title, transcript, meta=None)`, `to_txt(title, transcript, meta=None)` — include the meta block above the transcript.

- [ ] **Step 1: Write the failing prompt test**

Append to `tests/test_prompt.py` (create the file if absent, importing from `app.prompt.builder`):

```python
from app.prompt.builder import build_prompt, format_meta

_T = {"segments": [{"speaker": "SPEAKER_00", "start_ms": 0, "end_ms": 1000, "text": "안녕하세요"}],
      "full_text": "안녕하세요", "language": "ko"}


def test_format_meta_omits_empty_fields():
    out = format_meta({"location": "회의실 A", "attendees": "", "agenda": "킥오프"})
    assert "회의실 A" in out and "킥오프" in out
    assert "참석자" not in out  # empty omitted


def test_format_meta_blank_when_none():
    assert format_meta(None) == ""
    assert format_meta({"location": ""}) == ""


def test_build_prompt_includes_meta_block_before_transcript():
    bundle = build_prompt(_T, meta={"date": "2026-06-23", "time": "14:00", "location": "A"})
    assert "회의 정보" in bundle.prompt
    assert bundle.prompt.index("회의 정보") < bundle.prompt.index("안녕하세요")
    assert "2026-06-23 14:00" in bundle.prompt


def test_build_prompt_without_meta_unchanged():
    bundle = build_prompt(_T)
    assert "회의 정보" not in bundle.prompt
    assert "안녕하세요" in bundle.prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_prompt.py -q`
Expected: FAIL — `format_meta` not defined / `build_prompt` rejects `meta`.

- [ ] **Step 3: Implement `format_meta` + extend `build_prompt`**

In `app/prompt/builder.py`, add after `format_transcript`:

```python
def format_meta(meta) -> str:
    if not meta:
        return ""
    date_time = " ".join(p for p in [meta.get("date", ""), meta.get("time", "")] if p).strip()
    rows = [
        ("일자", date_time),
        ("장소", meta.get("location", "")),
        ("참석자", meta.get("attendees", "")),
        ("안건", meta.get("agenda", "")),
    ]
    lines = [f"- {label}: {value}" for label, value in rows if value]
    if not lines:
        return ""
    return "=== 회의 정보 ===\n" + "\n".join(lines) + "\n\n"
```

Change `build_prompt`:

```python
def build_prompt(transcript: dict, meta=None, *, too_long_threshold: int = 40000) -> PromptBundle:
    transcript_text = format_transcript(transcript)
    prompt = INSTRUCTION + format_meta(meta) + transcript_text
    return PromptBundle(
        prompt=prompt,
        transcript_text=transcript_text,
        char_count=len(prompt),
        too_long=len(prompt) > too_long_threshold,
    )
```

> `INSTRUCTION` already ends with `"=== 전사본 ===\n"`. Move that trailing `=== 전사본 ===\n` out of `INSTRUCTION` into the assembly so the meta block sits above it. Concretely: drop `"=== 전사본 ===\n"` from `INSTRUCTION` and build `prompt = INSTRUCTION + format_meta(meta) + "=== 전사본 ===\n" + transcript_text`. Update any existing prompt test that asserted on the old INSTRUCTION tail.

- [ ] **Step 4: Implement export meta**

In `app/export/markdown.py`:

```python
from app.prompt.builder import format_transcript, format_meta


def to_markdown(title: str, transcript: dict, meta=None) -> str:
    body = format_meta(meta) + format_transcript(transcript)
    return f"# {title}\n\n```\n{body}\n```\n"


def to_txt(title: str, transcript: dict, meta=None) -> str:
    body = format_meta(meta) + format_transcript(transcript)
    return f"{title}\n\n{body}\n"
```

- [ ] **Step 5: Wire meta through the API**

In `app/api/recordings.py`: in `get_prompt`, change to `build_prompt(rec.transcript, rec.meta).model_dump()`. In `export`, pass `rec.meta`: `to_markdown(rec.title, rec.transcript, rec.meta)` and `to_txt(rec.title, rec.transcript, rec.meta)`.

- [ ] **Step 6: Add an export meta test**

Append to `tests/test_export.py` (create if absent):

```python
from app.export.markdown import to_markdown, to_txt

_T = {"segments": [{"speaker": "SPEAKER_00", "start_ms": 0, "end_ms": 1000, "text": "hi"}],
      "full_text": "hi", "language": "ko"}


def test_export_includes_meta_block():
    md = to_markdown("회의", _T, {"location": "A"})
    assert "회의 정보" in md and "A" in md
    txt = to_txt("회의", _T, {"location": "A"})
    assert "회의 정보" in txt


def test_export_without_meta_has_no_block():
    assert "회의 정보" not in to_markdown("회의", _T)
```

- [ ] **Step 7: Run the full backend suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — all existing tests + the new meta tests. If an old prompt test asserted the exact INSTRUCTION string, update it to match the new assembly.

- [ ] **Step 8: Commit**

```bash
git add app/prompt/builder.py app/export/markdown.py app/api/recordings.py tests/test_prompt.py tests/test_export.py
git commit -m "feat(server): include 회의 정보 meta block in prompt and md/txt export"
```

---

# Phase B — Frontend SPA (confirmed dark-modern design)

All paths relative to repo root. Work in `web/`; run tests with `cd web && npm test`.

### Task B1: Scaffold Vite + React + TS + Vitest + design-system styles + types

**Files:**
- Create: `web/package.json`, `web/tsconfig.json`, `web/tsconfig.node.json`, `web/vite.config.ts`, `web/index.html`, `web/.gitignore`
- Create: `web/src/main.tsx`, `web/src/App.tsx`, `web/src/styles.css`, `web/src/test-setup.ts`, `web/src/lib/types.ts`
- Test: `web/src/App.test.tsx`

**Interfaces:**
- Produces:
  - `App` (named export) rendering the top bar with `<h1>` wordmark containing `V2M`.
  - `lib/types.ts`: `RecordingStatus`, `MeetingMeta`, `RecordingSummary`, `TranscriptSegment`, `Transcript`, `RecordingDetail`, `PromptBundle` (exact shapes below).
  - `npm test` runs Vitest; `npm run build` outputs `web/dist`.

**Environment setup (first task):** Create `web/` files, then `cd web && npm install`. `web/.gitignore` = `node_modules/` and `dist/`. Do not commit either.

- [ ] **Step 1: Create package.json**

`web/package.json`:

```json
{
  "name": "v2m-web",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "preview": "vite preview",
    "typecheck": "tsc --noEmit",
    "test": "vitest run"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.5.0",
    "@testing-library/react": "^16.0.1",
    "@testing-library/user-event": "^14.5.2",
    "@types/react": "^18.3.10",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.2",
    "jsdom": "^25.0.1",
    "typescript": "^5.6.2",
    "vite": "^5.4.8",
    "vitest": "^2.1.2"
  }
}
```

- [ ] **Step 2: Create TS + Vite config**

`web/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

`web/tsconfig.node.json`:

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "noEmit": true
  },
  "include": ["vite.config.ts"]
}
```

`web/vite.config.ts`:

```ts
/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
    },
  },
  build: { outDir: "dist" },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
});
```

- [ ] **Step 3: Create index.html, entry, test setup, types**

`web/index.html`:

```html
<!doctype html>
<html lang="ko">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>V2M</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`web/src/test-setup.ts`:

```ts
import "@testing-library/jest-dom";
```

`web/src/lib/types.ts`:

```ts
export type RecordingStatus = "recorded" | "transcribing" | "done" | "failed";

export interface MeetingMeta {
  date?: string;
  time?: string;
  location?: string;
  attendees?: string;
  agenda?: string;
}

export interface RecordingSummary {
  id: string;
  title: string;
  status: RecordingStatus;
  created_at: string;
  duration_sec: number | null;
  meta: MeetingMeta | null;
}

export interface TranscriptSegment {
  speaker: string;
  start_ms: number;
  end_ms: number;
  text: string;
}

export interface Transcript {
  segments: TranscriptSegment[];
  full_text: string;
  language: string;
}

export interface RecordingDetail {
  id: string;
  title: string;
  status: RecordingStatus;
  created_at: string;
  duration_sec: number | null;
  error: string | null;
  transcript: Transcript | null;
  meta: MeetingMeta | null;
}

export interface PromptBundle {
  prompt: string;
  transcript_text: string;
  char_count: number;
  too_long: boolean;
}
```

- [ ] **Step 4: Create the design-system stylesheet**

`web/src/styles.css` — ports [.superdesign/design-system.md](../../../.superdesign/design-system.md) tokens:

```css
:root {
  --bg: #0a0a0c; --panel: #0e0f13;
  --surface: rgba(255,255,255,.025); --surface-2: rgba(255,255,255,.045);
  --border: rgba(255,255,255,.08); --border-strong: rgba(255,255,255,.14);
  --text: #ededf2; --muted: rgba(237,237,242,.62); --faint: rgba(237,237,242,.40);
  --accent: #6366f1; --accent-bright: #818cf8; --accent-deep: #4338ca;
  --accent-soft: rgba(99,102,241,.16);
  --ok: #34d399; --ok-soft: rgba(52,211,153,.14);
  --info: #818cf8; --info-soft: rgba(129,140,248,.14);
  --warn: #fbbf24; --warn-soft: rgba(251,191,36,.14);
  --err: #f87171; --err-soft: rgba(248,113,113,.14);
  --font: "Pretendard","Inter",system-ui,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;
  --r-card: 14px; --r-field: 9px;
}
* { box-sizing: border-box; }
html, body { margin: 0; }
body {
  background: var(--bg); color: var(--text);
  font-family: var(--font); font-size: 15px; line-height: 1.5;
  letter-spacing: -0.01em;
}
body::before {
  content: ""; position: fixed; inset: 0; z-index: -1; pointer-events: none;
  background:
    radial-gradient(620px 320px at 50% -8%, rgba(99,102,241,.20), transparent 70%),
    radial-gradient(500px 300px at 90% 0%, rgba(139,92,246,.12), transparent 70%);
}
::selection { background: var(--accent-soft); }
.num { font-variant-numeric: tabular-nums; }

.topbar {
  position: sticky; top: 0; z-index: 10;
  display: flex; align-items: center; gap: 12px;
  padding: 14px 24px; backdrop-filter: blur(12px);
  background: rgba(10,10,12,.72); border-bottom: 1px solid var(--border);
}
.logo {
  width: 30px; height: 30px; border-radius: 8px; display: grid; place-items: center;
  font-weight: 700; color: #fff;
  background: linear-gradient(135deg, var(--accent), var(--accent-deep));
  box-shadow: 0 0 0 1px rgba(99,102,241,.35), 0 18px 60px -24px rgba(99,102,241,.55);
}
.wordmark { font-size: 22px; font-weight: 700; letter-spacing: -0.02em; }
.tagline { color: var(--muted); font-size: 12px; }

.container { max-width: 840px; margin: 0 auto; padding: 24px 24px 64px; }
.card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--r-card); padding: 22px; margin-bottom: 20px;
}
.card h2 { font-size: 16px; font-weight: 650; margin: 0 0 16px; }

.field { display: flex; flex-direction: column; gap: 6px; }
.field label { color: var(--muted); font-size: 13px; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
input, textarea {
  width: 100%; background: rgba(255,255,255,.03); color: var(--text);
  border: 1px solid var(--border); border-radius: var(--r-field);
  padding: 9px 11px; font: inherit; color-scheme: dark;
}
textarea { resize: vertical; min-height: 72px; }
input:focus, textarea:focus {
  outline: none; border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.btn {
  display: inline-flex; align-items: center; gap: 8px; cursor: pointer;
  border-radius: var(--r-field); padding: 9px 14px; font: inherit; font-weight: 600;
  border: 1px solid transparent; transition: filter .15s ease, transform .15s ease;
}
.btn-primary {
  color: #fff; border: none;
  background: linear-gradient(135deg, var(--accent), var(--accent-deep));
  box-shadow: 0 0 0 1px rgba(99,102,241,.35), 0 18px 60px -24px rgba(99,102,241,.55);
}
.btn-primary:hover { filter: brightness(1.08); transform: translateY(-1px); }
.btn-secondary { background: transparent; color: var(--text); border: 1px solid var(--border-strong); }
.btn-danger-ghost { background: transparent; color: var(--err); border: none; }
.btn:disabled { opacity: .5; cursor: default; }

.recorder { display: flex; align-items: center; gap: 16px; margin-top: 8px; }
.rec-dot { width: 10px; height: 10px; border-radius: 999px; background: var(--err);
  box-shadow: 0 0 12px var(--err); animation: pulse 1.4s ease-in-out infinite; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .35; } }
.timer { font-size: 28px; font-weight: 700; font-variant-numeric: tabular-nums; }

.badge { display: inline-flex; align-items: center; padding: 2px 10px; border-radius: 999px;
  font-size: 12px; font-weight: 600; }
.badge-done { background: var(--ok-soft); color: var(--ok); border: 1px solid rgba(52,211,153,.25); }
.badge-transcribing { background: var(--info-soft); color: var(--info); border: 1px solid rgba(129,140,248,.25); }
.badge-recorded { background: var(--warn-soft); color: var(--warn); border: 1px solid rgba(251,191,36,.25); }
.badge-failed { background: var(--err-soft); color: var(--err); border: 1px solid rgba(248,113,113,.25); }

.row { display: flex; align-items: center; gap: 12px; padding: 12px 0; border-bottom: 1px solid var(--border); }
.row:hover { background: var(--surface-2); }
.row .title { background: none; border: none; color: var(--text); font: inherit; font-weight: 600;
  cursor: pointer; text-align: left; flex: 0 0 auto; }
.row .sub { color: var(--muted); font-size: 13px; flex: 1; }
.empty { color: var(--muted); padding: 16px 0; }

.transcript { background: rgba(0,0,0,.25); border: 1px solid var(--border); border-radius: var(--r-field);
  max-height: 360px; overflow-y: auto; padding: 14px; }
.transcript .seg { margin-bottom: 14px; }
.transcript .head { display: flex; gap: 8px; align-items: baseline; margin-bottom: 4px; }
.speaker-chip { background: var(--accent-soft); color: var(--info); padding: 1px 8px; border-radius: 999px; font-size: 12px; }
.ts { color: var(--faint); font-size: 12px; font-variant-numeric: tabular-nums; }

.toast { position: fixed; left: 50%; bottom: 28px; transform: translateX(-50%);
  background: var(--ok-soft); color: var(--ok); border: 1px solid rgba(52,211,153,.25);
  padding: 10px 16px; border-radius: 999px; font-size: 14px; }
.warn-text { color: var(--warn); font-size: 13px; }
.btn-group { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 12px; }
```

- [ ] **Step 5: Write the failing test**

`web/src/App.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { App } from "./App";

describe("App", () => {
  it("renders the V2M wordmark", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /V2M/ })).toBeInTheDocument();
  });
});
```

- [ ] **Step 6: Run install + test to verify it fails**

Run: `cd web && npm install && npm test`
Expected: FAIL — `App.tsx` does not exist.

- [ ] **Step 7: Create minimal entry + App + gitignore**

`web/src/App.tsx`:

```tsx
export function App() {
  return (
    <>
      <header className="topbar">
        <span className="logo">V</span>
        <h1 className="wordmark">V2M</h1>
        <span className="tagline">음성에서 회의록까지</span>
      </header>
      <main className="container" />
    </>
  );
}
```

`web/src/main.tsx`:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

`web/.gitignore`:

```
node_modules/
dist/
```

- [ ] **Step 8: Run test + build to verify**

Run: `cd web && npm test && npm run build`
Expected: test PASS (1); build creates `web/dist/index.html`.

- [ ] **Step 9: Commit**

```bash
git add web/package.json web/tsconfig.json web/tsconfig.node.json web/vite.config.ts web/index.html web/.gitignore web/src/main.tsx web/src/App.tsx web/src/styles.css web/src/test-setup.ts web/src/lib/types.ts web/src/App.test.tsx
git commit -m "feat(web): scaffold Vite+React+TS, design-system styles, shared types"
```

---

### Task B2: API client + format helpers (with meta)

**Files:**
- Create: `web/src/lib/api.ts`, `web/src/lib/format.ts`
- Test: `web/src/lib/api.test.ts`, `web/src/lib/format.test.ts`

**Interfaces:**
- Consumes: `lib/types.ts`.
- Produces (`lib/api.ts`):
  - `listRecordings(): Promise<RecordingSummary[]>`
  - `getRecording(id): Promise<RecordingDetail>`
  - `uploadRecording(blob: Blob, opts?: { title?: string; meta?: MeetingMeta }): Promise<RecordingSummary>`
  - `patchRecording(id, body: { title?: string; meta?: MeetingMeta }): Promise<RecordingDetail>`
  - `retryRecording(id): Promise<void>`
  - `deleteRecording(id): Promise<void>`
  - `getPrompt(id): Promise<PromptBundle>`
  - `exportUrl(id, format: "md" | "txt"): string`
- Produces (`lib/format.ts`):
  - `msToMmss(ms: number): string`
  - `statusLabel(status: RecordingStatus): string` (Korean)
  - `attendeesCount(meta: MeetingMeta | null): number` — count of comma-separated non-empty names in `meta.attendees`.

- [ ] **Step 1: Write the failing format test**

`web/src/lib/format.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { msToMmss, statusLabel, attendeesCount } from "./format";

describe("format", () => {
  it("formats ms as mm:ss", () => {
    expect(msToMmss(0)).toBe("00:00");
    expect(msToMmss(65000)).toBe("01:05");
  });
  it("maps status to Korean labels", () => {
    expect(statusLabel("recorded")).toBe("대기");
    expect(statusLabel("transcribing")).toBe("전사중");
    expect(statusLabel("done")).toBe("완료");
    expect(statusLabel("failed")).toBe("실패");
  });
  it("counts attendees", () => {
    expect(attendeesCount(null)).toBe(0);
    expect(attendeesCount({ attendees: "홍길동, 김철수 ,  " })).toBe(2);
  });
});
```

- [ ] **Step 2: Write the failing api test**

`web/src/lib/api.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import * as api from "./api";

function mockFetch(body: unknown, ok = true, status = 200) {
  return vi.fn().mockResolvedValue({ ok, status, json: () => Promise.resolve(body) });
}

beforeEach(() => vi.stubGlobal("fetch", mockFetch([])));
afterEach(() => vi.unstubAllGlobals());

describe("api", () => {
  it("listRecordings GETs /api/recordings", async () => {
    const f = mockFetch([{ id: "1" }]);
    vi.stubGlobal("fetch", f);
    await api.listRecordings();
    expect(f).toHaveBeenCalledWith("/api/recordings");
  });

  it("uploadRecording POSTs multipart with file, title and meta JSON", async () => {
    const f = mockFetch({ id: "1" }, true, 201);
    vi.stubGlobal("fetch", f);
    await api.uploadRecording(new Blob(["a"]), { title: "T", meta: { location: "A" } });
    const [url, opts] = f.mock.calls[0];
    expect(url).toBe("/api/recordings");
    expect(opts.method).toBe("POST");
    const form = opts.body as FormData;
    expect(form.get("title")).toBe("T");
    expect(JSON.parse(form.get("meta") as string)).toEqual({ location: "A" });
    expect(form.get("file")).toBeInstanceOf(File);
  });

  it("patchRecording PATCHes JSON body", async () => {
    const f = mockFetch({ id: "1", title: "T2" }, true, 200);
    vi.stubGlobal("fetch", f);
    await api.patchRecording("1", { title: "T2", meta: { agenda: "x" } });
    const [url, opts] = f.mock.calls[0];
    expect(url).toBe("/api/recordings/1");
    expect(opts.method).toBe("PATCH");
    expect(opts.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(opts.body)).toEqual({ title: "T2", meta: { agenda: "x" } });
  });

  it("deleteRecording tolerates 204", async () => {
    vi.stubGlobal("fetch", mockFetch(null, false, 204));
    await expect(api.deleteRecording("1")).resolves.toBeUndefined();
  });

  it("throws on non-ok", async () => {
    vi.stubGlobal("fetch", mockFetch({}, false, 500));
    await expect(api.listRecordings()).rejects.toThrow(/500/);
  });

  it("exportUrl builds a query string", () => {
    expect(api.exportUrl("abc", "md")).toBe("/api/recordings/abc/export?format=md");
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd web && npm test -- src/lib`
Expected: FAIL — `./format` and `./api` not found.

- [ ] **Step 4: Implement format**

`web/src/lib/format.ts`:

```ts
import type { MeetingMeta, RecordingStatus } from "./types";

export function msToMmss(ms: number): string {
  const total = Math.floor(ms / 1000);
  const m = String(Math.floor(total / 60)).padStart(2, "0");
  const s = String(total % 60).padStart(2, "0");
  return `${m}:${s}`;
}

const STATUS_LABELS: Record<RecordingStatus, string> = {
  recorded: "대기",
  transcribing: "전사중",
  done: "완료",
  failed: "실패",
};

export function statusLabel(status: RecordingStatus): string {
  return STATUS_LABELS[status];
}

export function attendeesCount(meta: MeetingMeta | null): number {
  if (!meta?.attendees) return 0;
  return meta.attendees.split(",").map((s) => s.trim()).filter(Boolean).length;
}
```

- [ ] **Step 5: Implement api**

`web/src/lib/api.ts`:

```ts
import type { MeetingMeta, PromptBundle, RecordingDetail, RecordingSummary } from "./types";

async function jsonOrThrow<T>(resp: Response): Promise<T> {
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return (await resp.json()) as T;
}

export async function listRecordings(): Promise<RecordingSummary[]> {
  return jsonOrThrow(await fetch("/api/recordings"));
}

export async function getRecording(id: string): Promise<RecordingDetail> {
  return jsonOrThrow(await fetch(`/api/recordings/${id}`));
}

export async function uploadRecording(
  blob: Blob,
  opts: { title?: string; meta?: MeetingMeta } = {},
): Promise<RecordingSummary> {
  const form = new FormData();
  form.append("file", new File([blob], "recording.webm", { type: blob.type || "audio/webm" }));
  if (opts.title) form.append("title", opts.title);
  if (opts.meta) form.append("meta", JSON.stringify(opts.meta));
  return jsonOrThrow(await fetch("/api/recordings", { method: "POST", body: form }));
}

export async function patchRecording(
  id: string,
  body: { title?: string; meta?: MeetingMeta },
): Promise<RecordingDetail> {
  return jsonOrThrow(
    await fetch(`/api/recordings/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function retryRecording(id: string): Promise<void> {
  const resp = await fetch(`/api/recordings/${id}/retry`, { method: "POST" });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
}

export async function deleteRecording(id: string): Promise<void> {
  const resp = await fetch(`/api/recordings/${id}`, { method: "DELETE" });
  if (!resp.ok && resp.status !== 204) throw new Error(`HTTP ${resp.status}`);
}

export async function getPrompt(id: string): Promise<PromptBundle> {
  return jsonOrThrow(await fetch(`/api/recordings/${id}/prompt`));
}

export function exportUrl(id: string, format: "md" | "txt"): string {
  return `/api/recordings/${id}/export?format=${format}`;
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd web && npm test -- src/lib`
Expected: PASS (format 3 + api 6).

- [ ] **Step 7: Commit**

```bash
git add web/src/lib/api.ts web/src/lib/format.ts web/src/lib/api.test.ts web/src/lib/format.test.ts
git commit -m "feat(web): typed API client (meta upload + patch) + format helpers"
```

---

### Task B3: useRecorder hook (MediaRecorder)

**Files:**
- Create: `web/src/hooks/useRecorder.ts`
- Test: `web/src/hooks/useRecorder.test.ts`

**Interfaces:**
- Produces: `useRecorder(): { isRecording: boolean; elapsedMs: number; start(): Promise<void>; stop(): Promise<Blob> }`. `start()` → `getUserMedia({audio:true})`, opus when supported, 1s timeslice, elapsed timer. `stop()` → assembled `Blob`, stops tracks, clears timer.

- [ ] **Step 1: Write the failing test**

`web/src/hooks/useRecorder.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useRecorder } from "./useRecorder";

class FakeMediaRecorder {
  static isTypeSupported() { return true; }
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  mimeType = "audio/webm;codecs=opus";
  state = "inactive";
  constructor(public stream: { getTracks: () => { stop: () => void }[] }) {}
  start() { this.state = "recording"; this.ondataavailable?.({ data: new Blob(["chunk"], { type: this.mimeType }) }); }
  stop() { this.state = "inactive"; this.onstop?.(); }
}

beforeEach(() => {
  vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
  vi.stubGlobal("navigator", {
    mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] }) },
  });
});
afterEach(() => vi.unstubAllGlobals());

describe("useRecorder", () => {
  it("records then returns a blob on stop", async () => {
    const { result } = renderHook(() => useRecorder());
    await act(async () => { await result.current.start(); });
    expect(result.current.isRecording).toBe(true);
    let blob: Blob = new Blob();
    await act(async () => { blob = await result.current.stop(); });
    expect(result.current.isRecording).toBe(false);
    expect(blob.size).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test -- src/hooks/useRecorder`
Expected: FAIL — `./useRecorder` not found.

- [ ] **Step 3: Implement the hook**

`web/src/hooks/useRecorder.ts`:

```ts
import { useCallback, useRef, useState } from "react";

const MIME = "audio/webm;codecs=opus";

export interface UseRecorder {
  isRecording: boolean;
  elapsedMs: number;
  start: () => Promise<void>;
  stop: () => Promise<Blob>;
}

export function useRecorder(): UseRecorder {
  const [isRecording, setIsRecording] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);
  const startedAtRef = useRef(0);

  const start = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mime = MediaRecorder.isTypeSupported(MIME) ? MIME : "";
    const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    chunksRef.current = [];
    rec.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
    rec.start(1000);
    recorderRef.current = rec;
    startedAtRef.current = Date.now();
    setElapsedMs(0);
    setIsRecording(true);
    timerRef.current = window.setInterval(() => setElapsedMs(Date.now() - startedAtRef.current), 250);
  }, []);

  const stop = useCallback(() => {
    return new Promise<Blob>((resolve) => {
      const rec = recorderRef.current;
      if (!rec) { resolve(new Blob()); return; }
      rec.onstop = () => {
        if (timerRef.current) window.clearInterval(timerRef.current);
        rec.stream.getTracks().forEach((t) => t.stop());
        setIsRecording(false);
        resolve(new Blob(chunksRef.current, { type: rec.mimeType || MIME }));
      };
      rec.stop();
    });
  }, []);

  return { isRecording, elapsedMs, start, stop };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm test -- src/hooks/useRecorder`
Expected: PASS (1).

- [ ] **Step 5: Commit**

```bash
git add web/src/hooks/useRecorder.ts web/src/hooks/useRecorder.test.ts
git commit -m "feat(web): useRecorder MediaRecorder hook"
```

---

### Task B4: useRecordings hook (list + adaptive polling)

**Files:**
- Create: `web/src/hooks/useRecordings.ts`
- Test: `web/src/hooks/useRecordings.test.ts`

**Interfaces:**
- Consumes: `api.listRecordings`, `types.RecordingSummary`.
- Produces: `useRecordings(): { recordings: RecordingSummary[]; loading: boolean; refresh(): Promise<RecordingSummary[]> }`. Loads on mount; polls 3s while any row is `recorded`/`transcribing`, else 12s; `refresh()` re-fetches immediately.

- [ ] **Step 1: Write the failing test**

`web/src/hooks/useRecordings.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";

vi.mock("../lib/api", () => ({ listRecordings: vi.fn() }));
import { listRecordings } from "../lib/api";
import { useRecordings } from "./useRecordings";

const sample = [{ id: "a", title: "T", status: "done", created_at: "x", duration_sec: null, meta: null }];

beforeEach(() => {
  vi.clearAllMocks();
  (listRecordings as ReturnType<typeof vi.fn>).mockResolvedValue(sample);
});

describe("useRecordings", () => {
  it("loads recordings on mount", async () => {
    const { result } = renderHook(() => useRecordings());
    await waitFor(() => expect(result.current.recordings).toEqual(sample));
    expect(result.current.loading).toBe(false);
  });

  it("refresh re-fetches", async () => {
    const { result } = renderHook(() => useRecordings());
    await waitFor(() => expect(result.current.recordings).toEqual(sample));
    await act(async () => { await result.current.refresh(); });
    expect(listRecordings).toHaveBeenCalledTimes(2);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test -- src/hooks/useRecordings`
Expected: FAIL — `./useRecordings` not found.

- [ ] **Step 3: Implement the hook**

`web/src/hooks/useRecordings.ts`:

```ts
import { useCallback, useEffect, useRef, useState } from "react";
import { listRecordings } from "../lib/api";
import type { RecordingSummary } from "../lib/types";

const ACTIVE_POLL_MS = 3000;
const IDLE_POLL_MS = 12000;

export function useRecordings() {
  const [recordings, setRecordings] = useState<RecordingSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const timerRef = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    const rows = await listRecordings();
    setRecordings(rows);
    setLoading(false);
    return rows;
  }, []);

  useEffect(() => {
    let active = true;
    async function tick() {
      const rows = await refresh().catch(() => [] as RecordingSummary[]);
      if (!active) return;
      const busy = rows.some((r) => r.status === "recorded" || r.status === "transcribing");
      timerRef.current = window.setTimeout(tick, busy ? ACTIVE_POLL_MS : IDLE_POLL_MS);
    }
    tick();
    return () => { active = false; if (timerRef.current) window.clearTimeout(timerRef.current); };
  }, [refresh]);

  return { recordings, loading, refresh };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm test -- src/hooks/useRecordings`
Expected: PASS (2).

- [ ] **Step 5: Commit**

```bash
git add web/src/hooks/useRecordings.ts web/src/hooks/useRecordings.test.ts
git commit -m "feat(web): useRecordings list + adaptive polling hook"
```

---

### Task B5: MeetingForm (shared create/edit form)

**Files:**
- Create: `web/src/features/meeting/MeetingForm.tsx`
- Test: `web/src/features/meeting/MeetingForm.test.tsx`

**Interfaces:**
- Consumes: `types.MeetingMeta`.
- Produces: `MeetingForm({ title, meta, onChange })` where `onChange: (next: { title: string; meta: MeetingMeta }) => void`. Renders a controlled form: 제목·일자(`type="date"`)·시간(`type="time"`)·장소 in a 2-col grid, 참석자·안건 full width (`textarea`). Every edit calls `onChange` with the full `{title, meta}` snapshot. Inputs use design-system field classes. Labels: 제목, 일자, 시간, 장소, 참석자, 안건/목적.

- [ ] **Step 1: Write the failing test**

`web/src/features/meeting/MeetingForm.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MeetingForm } from "./MeetingForm";

describe("MeetingForm", () => {
  it("renders fields and emits changes", async () => {
    const onChange = vi.fn();
    render(<MeetingForm title="" meta={{}} onChange={onChange} />);
    expect(screen.getByLabelText("제목")).toBeInTheDocument();
    expect(screen.getByLabelText("장소")).toBeInTheDocument();
    expect(screen.getByLabelText("참석자")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("장소"), "A");
    expect(onChange).toHaveBeenLastCalledWith({ title: "", meta: { location: "A" } });
  });

  it("shows existing values", () => {
    render(<MeetingForm title="주간회의" meta={{ location: "B룸" }} onChange={vi.fn()} />);
    expect(screen.getByLabelText("제목")).toHaveValue("주간회의");
    expect(screen.getByLabelText("장소")).toHaveValue("B룸");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test -- src/features/meeting`
Expected: FAIL — `./MeetingForm` not found.

- [ ] **Step 3: Implement the component**

`web/src/features/meeting/MeetingForm.tsx`:

```tsx
import type { MeetingMeta } from "../../lib/types";

interface Props {
  title: string;
  meta: MeetingMeta;
  onChange: (next: { title: string; meta: MeetingMeta }) => void;
}

export function MeetingForm({ title, meta, onChange }: Props) {
  function setMeta(key: keyof MeetingMeta, value: string) {
    const next = { ...meta };
    if (value) next[key] = value;
    else delete next[key];
    onChange({ title, meta: next });
  }

  return (
    <div className="meeting-form">
      <div className="grid-2">
        <div className="field">
          <label htmlFor="mf-title">제목</label>
          <input id="mf-title" value={title}
            onChange={(e) => onChange({ title: e.target.value, meta })} />
        </div>
        <div className="field">
          <label htmlFor="mf-date">일자</label>
          <input id="mf-date" type="date" value={meta.date ?? ""}
            onChange={(e) => setMeta("date", e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="mf-time">시간</label>
          <input id="mf-time" type="time" value={meta.time ?? ""}
            onChange={(e) => setMeta("time", e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="mf-loc">장소</label>
          <input id="mf-loc" value={meta.location ?? ""}
            onChange={(e) => setMeta("location", e.target.value)} />
        </div>
      </div>
      <div className="field" style={{ marginTop: 14 }}>
        <label htmlFor="mf-att">참석자</label>
        <textarea id="mf-att" value={meta.attendees ?? ""}
          placeholder="쉼표로 구분 (예: 홍길동, 김철수)"
          onChange={(e) => setMeta("attendees", e.target.value)} />
      </div>
      <div className="field" style={{ marginTop: 14 }}>
        <label htmlFor="mf-agenda">안건/목적</label>
        <textarea id="mf-agenda" value={meta.agenda ?? ""}
          onChange={(e) => setMeta("agenda", e.target.value)} />
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm test -- src/features/meeting`
Expected: PASS (2).

- [ ] **Step 5: Commit**

```bash
git add web/src/features/meeting/MeetingForm.tsx web/src/features/meeting/MeetingForm.test.tsx
git commit -m "feat(web): shared MeetingForm (create/edit meeting metadata)"
```

---

### Task B6: RecorderPanel (timer + start/stop + upload with meta)

**Files:**
- Create: `web/src/features/recorder/RecorderPanel.tsx`
- Test: `web/src/features/recorder/RecorderPanel.test.tsx`

**Interfaces:**
- Consumes: `useRecorder`, `api.uploadRecording`, `format.msToMmss`, `types.MeetingMeta`.
- Produces: `RecorderPanel({ title, meta, onUploaded })` where `onUploaded: () => void`. Shows the pulse dot (while recording), the elapsed timer (`.num`), and a 녹음 시작 / 녹음 정지 toggle. On stop it uploads the blob with `{ title, meta }`, then calls `onUploaded`. Shows a mic-permission error on `start()` failure and an upload error on failure.

- [ ] **Step 1: Write the failing test**

`web/src/features/recorder/RecorderPanel.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RecorderPanel } from "./RecorderPanel";

const startMock = vi.fn().mockResolvedValue(undefined);
const stopMock = vi.fn().mockResolvedValue(new Blob(["x"]));
const recorderState = { isRecording: false, elapsedMs: 0, start: startMock, stop: stopMock };

vi.mock("../../hooks/useRecorder", () => ({ useRecorder: () => recorderState }));
vi.mock("../../lib/api", () => ({ uploadRecording: vi.fn().mockResolvedValue({ id: "1" }) }));
import { uploadRecording } from "../../lib/api";

beforeEach(() => { vi.clearAllMocks(); recorderState.isRecording = false; });

describe("RecorderPanel", () => {
  it("starts recording on click", async () => {
    render(<RecorderPanel title="회의" meta={{}} onUploaded={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "녹음 시작" }));
    expect(startMock).toHaveBeenCalled();
  });

  it("uploads with title+meta and notifies on stop", async () => {
    recorderState.isRecording = true;
    const onUploaded = vi.fn();
    render(<RecorderPanel title="회의" meta={{ location: "A" }} onUploaded={onUploaded} />);
    await userEvent.click(screen.getByRole("button", { name: "녹음 정지" }));
    await waitFor(() => expect(uploadRecording).toHaveBeenCalled());
    const [, opts] = (uploadRecording as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(opts).toEqual({ title: "회의", meta: { location: "A" } });
    expect(onUploaded).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test -- src/features/recorder`
Expected: FAIL — `./RecorderPanel` not found.

- [ ] **Step 3: Implement the component**

`web/src/features/recorder/RecorderPanel.tsx`:

```tsx
import { useState } from "react";
import { useRecorder } from "../../hooks/useRecorder";
import { uploadRecording } from "../../lib/api";
import { msToMmss } from "../../lib/format";
import type { MeetingMeta } from "../../lib/types";

interface Props { title: string; meta: MeetingMeta; onUploaded: () => void; }

export function RecorderPanel({ title, meta, onUploaded }: Props) {
  const { isRecording, elapsedMs, start, stop } = useRecorder();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleStart() {
    setError(null);
    try { await start(); } catch { setError("마이크 권한이 필요합니다."); }
  }

  async function handleStop() {
    setBusy(true);
    setError(null);
    try {
      const blob = await stop();
      await uploadRecording(blob, { title, meta });
      onUploaded();
    } catch { setError("업로드에 실패했습니다."); }
    finally { setBusy(false); }
  }

  return (
    <div className="recorder">
      {isRecording && <span className="rec-dot" aria-hidden="true" />}
      <span className="timer num">{msToMmss(elapsedMs)}</span>
      {!isRecording ? (
        <button className="btn btn-primary" onClick={handleStart} disabled={busy}>녹음 시작</button>
      ) : (
        <button className="btn btn-secondary" onClick={handleStop} disabled={busy}>녹음 정지</button>
      )}
      {error && <p role="alert" className="warn-text">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm test -- src/features/recorder`
Expected: PASS (2).

- [ ] **Step 5: Commit**

```bash
git add web/src/features/recorder/RecorderPanel.tsx web/src/features/recorder/RecorderPanel.test.tsx
git commit -m "feat(web): RecorderPanel record + upload with meeting meta"
```

---

### Task B7: StatusBadge + RecordingList

**Files:**
- Create: `web/src/features/recordings/StatusBadge.tsx`, `web/src/features/recordings/RecordingList.tsx`
- Test: `web/src/features/recordings/RecordingList.test.tsx`

**Interfaces:**
- Consumes: `types.RecordingSummary/RecordingStatus`, `format.statusLabel/attendeesCount`.
- Produces:
  - `StatusBadge({ status })` → `<span class="badge badge-<status>">{statusLabel}</span>`.
  - `RecordingList({ recordings, onSelect, onDelete })`, `onSelect/onDelete: (id) => void`. Empty state: "아직 회의가 없습니다." Each row: title button (select) + sub `일자 · 참석 N명` + status badge + delete button (`aria-label` = `<title> 삭제`).

- [ ] **Step 1: Write the failing test**

`web/src/features/recordings/RecordingList.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RecordingList } from "./RecordingList";
import type { RecordingSummary } from "../../lib/types";

const rows: RecordingSummary[] = [
  { id: "a", title: "주간회의", status: "done", created_at: "x", duration_sec: 60,
    meta: { date: "2026-06-23", attendees: "홍길동, 김철수" } },
  { id: "b", title: "스프린트", status: "transcribing", created_at: "y", duration_sec: null, meta: null },
];

describe("RecordingList", () => {
  it("shows empty state", () => {
    render(<RecordingList recordings={[]} onSelect={vi.fn()} onDelete={vi.fn()} />);
    expect(screen.getByText("아직 회의가 없습니다.")).toBeInTheDocument();
  });

  it("renders rows + sub text and fires select/delete", async () => {
    const onSelect = vi.fn();
    const onDelete = vi.fn();
    render(<RecordingList recordings={rows} onSelect={onSelect} onDelete={onDelete} />);
    expect(screen.getByText("완료")).toBeInTheDocument();
    expect(screen.getByText(/참석 2명/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "주간회의" }));
    expect(onSelect).toHaveBeenCalledWith("a");
    await userEvent.click(screen.getByRole("button", { name: "스프린트 삭제" }));
    expect(onDelete).toHaveBeenCalledWith("b");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test -- src/features/recordings/RecordingList`
Expected: FAIL — components not found.

- [ ] **Step 3: Implement StatusBadge**

`web/src/features/recordings/StatusBadge.tsx`:

```tsx
import type { RecordingStatus } from "../../lib/types";
import { statusLabel } from "../../lib/format";

export function StatusBadge({ status }: { status: RecordingStatus }) {
  return <span className={`badge badge-${status}`}>{statusLabel(status)}</span>;
}
```

- [ ] **Step 4: Implement RecordingList**

`web/src/features/recordings/RecordingList.tsx`:

```tsx
import type { RecordingSummary } from "../../lib/types";
import { attendeesCount } from "../../lib/format";
import { StatusBadge } from "./StatusBadge";

function subText(r: RecordingSummary): string {
  const parts: string[] = [];
  if (r.meta?.date) parts.push(r.meta.date);
  const n = attendeesCount(r.meta);
  if (n > 0) parts.push(`참석 ${n}명`);
  return parts.join(" · ");
}

export function RecordingList({
  recordings, onSelect, onDelete,
}: {
  recordings: RecordingSummary[];
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  if (recordings.length === 0) return <p className="empty">아직 회의가 없습니다.</p>;
  return (
    <div className="recording-list">
      {recordings.map((r) => (
        <div className="row" key={r.id}>
          <button className="title" onClick={() => onSelect(r.id)}>{r.title}</button>
          <span className="sub">{subText(r)}</span>
          <StatusBadge status={r.status} />
          <button className="btn btn-danger-ghost" aria-label={`${r.title} 삭제`}
            onClick={() => onDelete(r.id)}>삭제</button>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd web && npm test -- src/features/recordings/RecordingList`
Expected: PASS (2).

- [ ] **Step 6: Commit**

```bash
git add web/src/features/recordings/StatusBadge.tsx web/src/features/recordings/RecordingList.tsx web/src/features/recordings/RecordingList.test.tsx
git commit -m "feat(web): StatusBadge + RecordingList with meta sub-text"
```

---

### Task B8: CopyForClaude (copy + toast, no auto-open)

**Files:**
- Create: `web/src/features/recordings/CopyForClaude.tsx`
- Test: `web/src/features/recordings/CopyForClaude.test.tsx`

**Interfaces:**
- Consumes: `api.getPrompt`.
- Produces: `CopyForClaude({ id })`. On click: fetches the prompt bundle, writes `bundle.prompt` to the clipboard, shows a `role="status"` toast "복사되었습니다 (N자) — claude.ai 데스크탑 앱에 붙여넣으세요". **Never calls `window.open`.** If `bundle.too_long`, also shows a `role="alert"` warning to split the paste.

- [ ] **Step 1: Write the failing test**

`web/src/features/recordings/CopyForClaude.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CopyForClaude } from "./CopyForClaude";

vi.mock("../../lib/api", () => ({ getPrompt: vi.fn() }));
import { getPrompt } from "../../lib/api";

const writeText = vi.fn().mockResolvedValue(undefined);
const openSpy = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("navigator", { clipboard: { writeText } });
  vi.stubGlobal("open", openSpy);
});

describe("CopyForClaude", () => {
  it("copies the prompt, shows char count, and does NOT open a new tab", async () => {
    (getPrompt as ReturnType<typeof vi.fn>).mockResolvedValue({
      prompt: "PROMPT-TEXT", transcript_text: "t", char_count: 1240, too_long: false,
    });
    render(<CopyForClaude id="a" />);
    await userEvent.click(screen.getByRole("button", { name: /복사/ }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("PROMPT-TEXT"));
    expect(screen.getByRole("status")).toHaveTextContent(/복사되었습니다/);
    expect(screen.getByRole("status")).toHaveTextContent(/1,240자/);
    expect(openSpy).not.toHaveBeenCalled();
  });

  it("warns when too long", async () => {
    (getPrompt as ReturnType<typeof vi.fn>).mockResolvedValue({
      prompt: "x", transcript_text: "t", char_count: 99999, too_long: true,
    });
    render(<CopyForClaude id="a" />);
    await userEvent.click(screen.getByRole("button", { name: /복사/ }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/나눠서/));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test -- src/features/recordings/CopyForClaude`
Expected: FAIL — component not found.

- [ ] **Step 3: Implement the component**

`web/src/features/recordings/CopyForClaude.tsx`:

```tsx
import { useState } from "react";
import { getPrompt } from "../../lib/api";

export function CopyForClaude({ id }: { id: string }) {
  const [state, setState] = useState<"idle" | "copied" | "error">("idle");
  const [tooLong, setTooLong] = useState(false);
  const [charCount, setCharCount] = useState<number | null>(null);

  async function handleCopy() {
    try {
      const bundle = await getPrompt(id);
      await navigator.clipboard.writeText(bundle.prompt);
      setTooLong(bundle.too_long);
      setCharCount(bundle.char_count);
      setState("copied");
    } catch { setState("error"); }
  }

  return (
    <div className="copy-for-claude">
      <button className="btn btn-primary" onClick={handleCopy}>전사본 + 프롬프트 복사</button>
      {state === "copied" && charCount !== null && (
        <p role="status" className="toast">
          복사되었습니다 ({charCount.toLocaleString()}자) — claude.ai 데스크탑 앱에 붙여넣으세요
        </p>
      )}
      {tooLong && (
        <p role="alert" className="warn-text">
          전사본이 길어 claude.ai 입력 한도를 넘을 수 있습니다. 나눠서 붙여넣으세요.
        </p>
      )}
      {state === "error" && <p role="alert" className="warn-text">복사에 실패했습니다.</p>}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm test -- src/features/recordings/CopyForClaude`
Expected: PASS (2).

- [ ] **Step 5: Commit**

```bash
git add web/src/features/recordings/CopyForClaude.tsx web/src/features/recordings/CopyForClaude.test.tsx
git commit -m "feat(web): CopyForClaude clipboard + toast (no auto-open)"
```

---

### Task B9: RecordingDetail (meeting edit + save + transcript + copy/export + retry)

**Files:**
- Create: `web/src/features/recordings/RecordingDetail.tsx`
- Test: `web/src/features/recordings/RecordingDetail.test.tsx`

**Interfaces:**
- Consumes: `api.getRecording/patchRecording/retryRecording/exportUrl`, `format.msToMmss/statusLabel`, `StatusBadge`, `MeetingForm`, `CopyForClaude`, `types`.
- Produces:
  - `groupSegments(segments: TranscriptSegment[]): { speaker: string; startMs: number; lines: string[] }[]` (exported pure fn — merges consecutive same-speaker segments).
  - `RecordingDetail({ id, onBack })`. Loads detail; renders a back button, the editable `MeetingForm` (seeded from detail) with a 저장 button (`patchRecording`), the status badge; when `done`, renders `CopyForClaude` + export links + the grouped transcript; when `failed`, error + 다시 시도 (retry→reload); when `recorded`/`transcribing`, a waiting line.

- [ ] **Step 1: Write the failing test**

`web/src/features/recordings/RecordingDetail.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RecordingDetail, groupSegments } from "./RecordingDetail";

vi.mock("../../lib/api", () => ({
  getRecording: vi.fn(),
  patchRecording: vi.fn().mockResolvedValue({}),
  retryRecording: vi.fn().mockResolvedValue(undefined),
  exportUrl: (id: string, f: string) => `/api/recordings/${id}/export?format=${f}`,
}));
vi.mock("./CopyForClaude", () => ({ CopyForClaude: () => <div>copy-stub</div> }));
import { getRecording, patchRecording, retryRecording } from "../../lib/api";

const doneDetail = {
  id: "a", title: "주간회의", status: "done", created_at: "x", duration_sec: 60, error: null,
  meta: { location: "A" },
  transcript: {
    segments: [
      { speaker: "SPEAKER_00", start_ms: 0, end_ms: 2000, text: "안녕하세요" },
      { speaker: "SPEAKER_00", start_ms: 2000, end_ms: 4000, text: "시작합니다" },
      { speaker: "SPEAKER_01", start_ms: 65000, end_ms: 67000, text: "네" },
    ],
    full_text: "안녕하세요 시작합니다 네", language: "ko",
  },
};

beforeEach(() => vi.clearAllMocks());

describe("groupSegments", () => {
  it("merges consecutive same-speaker segments", () => {
    const groups = groupSegments(doneDetail.transcript.segments);
    expect(groups).toHaveLength(2);
    expect(groups[0].lines).toEqual(["안녕하세요", "시작합니다"]);
    expect(groups[1].speaker).toBe("SPEAKER_01");
  });
});

describe("RecordingDetail", () => {
  it("renders transcript + export link when done and saves meta", async () => {
    (getRecording as ReturnType<typeof vi.fn>).mockResolvedValue(doneDetail);
    render(<RecordingDetail id="a" onBack={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("안녕하세요")).toBeInTheDocument());
    expect(screen.getByText("SPEAKER_00")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Markdown/ }))
      .toHaveAttribute("href", "/api/recordings/a/export?format=md");

    await userEvent.click(screen.getByRole("button", { name: "저장" }));
    expect(patchRecording).toHaveBeenCalledWith("a", { title: "주간회의", meta: { location: "A" } });
  });

  it("shows retry on failed and reloads", async () => {
    (getRecording as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ ...doneDetail, status: "failed", transcript: null, error: "boom" })
      .mockResolvedValueOnce(doneDetail);
    render(<RecordingDetail id="a" onBack={vi.fn()} />);
    await waitFor(() => expect(screen.getByText(/boom/)).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    expect(retryRecording).toHaveBeenCalledWith("a");
    await waitFor(() => expect(screen.getByText("안녕하세요")).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test -- src/features/recordings/RecordingDetail`
Expected: FAIL — `./RecordingDetail` not found.

- [ ] **Step 3: Implement the component**

`web/src/features/recordings/RecordingDetail.tsx`:

```tsx
import { useEffect, useState } from "react";
import { exportUrl, getRecording, patchRecording, retryRecording } from "../../lib/api";
import type { MeetingMeta, RecordingDetail as Detail, TranscriptSegment } from "../../lib/types";
import { msToMmss, statusLabel } from "../../lib/format";
import { StatusBadge } from "./StatusBadge";
import { CopyForClaude } from "./CopyForClaude";
import { MeetingForm } from "../meeting/MeetingForm";

interface Group { speaker: string; startMs: number; lines: string[]; }

export function groupSegments(segments: TranscriptSegment[]): Group[] {
  const groups: Group[] = [];
  for (const seg of segments) {
    const last = groups[groups.length - 1];
    if (last && last.speaker === seg.speaker) last.lines.push(seg.text);
    else groups.push({ speaker: seg.speaker, startMs: seg.start_ms, lines: [seg.text] });
  }
  return groups;
}

export function RecordingDetail({ id, onBack }: { id: string; onBack: () => void }) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [title, setTitle] = useState("");
  const [meta, setMeta] = useState<MeetingMeta>({});
  const [saving, setSaving] = useState(false);

  async function load() {
    const d = await getRecording(id);
    setDetail(d);
    setTitle(d.title);
    setMeta(d.meta ?? {});
  }
  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [id]);

  if (!detail) return <p className="empty">불러오는 중…</p>;

  async function handleSave() {
    setSaving(true);
    try { await patchRecording(id, { title, meta }); } finally { setSaving(false); }
  }

  return (
    <div className="detail">
      <button className="btn btn-secondary" onClick={onBack}>← 목록</button>

      <div className="card">
        <h2>회의 정보 <StatusBadge status={detail.status} /></h2>
        <MeetingForm title={title} meta={meta}
          onChange={(next) => { setTitle(next.title); setMeta(next.meta); }} />
        <div className="btn-group">
          <button className="btn btn-secondary" onClick={handleSave} disabled={saving}>저장</button>
        </div>
      </div>

      {detail.status === "failed" && (
        <div className="card" role="alert">
          <p className="warn-text">전사 실패: {detail.error}</p>
          <button className="btn btn-secondary"
            onClick={async () => { await retryRecording(id); load(); }}>다시 시도</button>
        </div>
      )}

      {detail.status === "done" && detail.transcript && (
        <>
          <div className="card">
            <h2>회의록 만들기</h2>
            <p className="sub">전사본과 프롬프트를 복사해 claude.ai 데스크탑 앱에 붙여넣으세요.</p>
            <CopyForClaude id={id} />
            <div className="btn-group">
              <a className="btn btn-secondary" href={exportUrl(id, "md")}>Markdown 내보내기</a>
              <a className="btn btn-secondary" href={exportUrl(id, "txt")}>TXT 내보내기</a>
            </div>
          </div>

          <div className="card">
            <h2>전사본</h2>
            <div className="transcript">
              {groupSegments(detail.transcript.segments).map((g, i) => (
                <div className="seg" key={i}>
                  <div className="head">
                    <span className="speaker-chip">{g.speaker}</span>
                    <span className="ts">[{msToMmss(g.startMs)}]</span>
                  </div>
                  {g.lines.map((line, j) => <p key={j}>{line}</p>)}
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {(detail.status === "recorded" || detail.status === "transcribing") && (
        <p className="empty">{statusLabel(detail.status)}… 잠시만 기다려 주세요.</p>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm test -- src/features/recordings/RecordingDetail`
Expected: PASS (groupSegments 1 + RecordingDetail 2).

- [ ] **Step 5: Commit**

```bash
git add web/src/features/recordings/RecordingDetail.tsx web/src/features/recordings/RecordingDetail.test.tsx
git commit -m "feat(web): RecordingDetail meeting edit + transcript + copy/export + retry"
```

---

### Task B10: App integration (home ↔ detail) + build

**Files:**
- Modify: `web/src/App.tsx`
- Modify: `web/src/App.test.tsx` (replace the B1 smoke test)

**Interfaces:**
- Consumes: `useRecordings`, `api.deleteRecording`, `MeetingForm`, `RecorderPanel`, `RecordingList`, `RecordingDetail`.
- Produces: `App` — home view shows a "새 회의" card (`MeetingForm` draft + `RecorderPanel` seeded with the draft title/meta) and the "회의 목록" card (`RecordingList`); selecting a row switches to `RecordingDetail`; deleting refreshes; `onBack`/upload reset the draft and refresh. After upload, the draft form clears.

- [ ] **Step 1: Write the failing test**

Replace `web/src/App.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";

vi.mock("./lib/api", () => ({
  listRecordings: vi.fn().mockResolvedValue([
    { id: "a", title: "주간회의", status: "done", created_at: "x", duration_sec: 1, meta: null },
  ]),
  deleteRecording: vi.fn().mockResolvedValue(undefined),
  getRecording: vi.fn().mockResolvedValue({
    id: "a", title: "주간회의", status: "done", created_at: "x", duration_sec: 1, error: null, meta: null,
    transcript: { segments: [{ speaker: "SPEAKER_00", start_ms: 0, end_ms: 1000, text: "안녕" }], full_text: "안녕", language: "ko" },
  }),
  patchRecording: vi.fn().mockResolvedValue({}),
}));
vi.mock("./hooks/useRecorder", () => ({
  useRecorder: () => ({ isRecording: false, elapsedMs: 0, start: vi.fn(), stop: vi.fn() }),
}));
vi.mock("./features/recordings/CopyForClaude", () => ({ CopyForClaude: () => <div>copy</div> }));

beforeEach(() => vi.clearAllMocks());

describe("App", () => {
  it("shows home (new-meeting + list), then opens detail on select", async () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /V2M/ })).toBeInTheDocument();
    expect(screen.getByText("새 회의")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "녹음 시작" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "주간회의" })).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "주간회의" }));
    await waitFor(() => expect(screen.getByText("안녕")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "← 목록" })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test -- src/App`
Expected: FAIL — App renders only the top bar.

- [ ] **Step 3: Implement App**

Replace `web/src/App.tsx`:

```tsx
import { useState } from "react";
import { MeetingForm } from "./features/meeting/MeetingForm";
import { RecorderPanel } from "./features/recorder/RecorderPanel";
import { RecordingList } from "./features/recordings/RecordingList";
import { RecordingDetail } from "./features/recordings/RecordingDetail";
import { useRecordings } from "./hooks/useRecordings";
import { deleteRecording } from "./lib/api";
import type { MeetingMeta } from "./lib/types";

export function App() {
  const { recordings, refresh } = useRecordings();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [draftMeta, setDraftMeta] = useState<MeetingMeta>({});

  async function handleDelete(id: string) {
    await deleteRecording(id);
    if (selectedId === id) setSelectedId(null);
    refresh();
  }

  function handleUploaded() {
    setDraftTitle("");
    setDraftMeta({});
    refresh();
  }

  return (
    <>
      <header className="topbar">
        <span className="logo">V</span>
        <h1 className="wordmark">V2M</h1>
        <span className="tagline">음성에서 회의록까지</span>
      </header>
      <main className="container">
        {selectedId ? (
          <RecordingDetail id={selectedId}
            onBack={() => { setSelectedId(null); refresh(); }} />
        ) : (
          <>
            <div className="card">
              <h2>새 회의</h2>
              <MeetingForm title={draftTitle} meta={draftMeta}
                onChange={(next) => { setDraftTitle(next.title); setDraftMeta(next.meta); }} />
              <RecorderPanel title={draftTitle} meta={draftMeta} onUploaded={handleUploaded} />
            </div>
            <div className="card">
              <h2>회의 목록</h2>
              <RecordingList recordings={recordings} onSelect={setSelectedId} onDelete={handleDelete} />
            </div>
          </>
        )}
      </main>
    </>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm test -- src/App`
Expected: PASS (1).

- [ ] **Step 5: Run the full suite + build**

Run: `cd web && npm test && npm run build`
Expected: all tests PASS; `web/dist/index.html` produced.

- [ ] **Step 6: Commit**

```bash
git add web/src/App.tsx web/src/App.test.tsx
git commit -m "feat(web): wire home (new-meeting + list) and detail views"
```

---

## Self-Review

**Spec coverage ([v2m-frontend-design.md](../specs/v2m-frontend-design.md)):**
- §3 backend meta: column+repo (A1), POST/GET/list (A2), PATCH (A3), prompt+export block (A4). ✓
- §4.1 home: new-meeting card (MeetingForm + RecorderPanel) + list — B5, B6, B7, B10. ✓
- §4.2 detail: editable meeting form + save (PATCH) + 회의록 만들기 (copy + export) + transcript + retry — B9 + B8. ✓
- §3.3 meta flows to claude.ai context — A4 prompt block; copy bundle uses `/prompt`. ✓
- §5 architecture / file structure — Tasks B1–B10 match. ✓
- §6 testing: backend meta tests (A1–A4), frontend unit tests (B2–B10); copy asserts no auto-open (B8). ✓
- Design fidelity: single font/no mono, indigo accent, 4 status colors, no auto-open — styles.css (B1) + B8. ✓

**Deferred (documented, non-blocking):** Playwright E2E (needs real ffmpeg+WhisperX server); first-run model-download UI / settings page. Both per spec §6.

**Placeholder scan:** No TBD/TODO; every code step shows full code + exact commands. The one prose note (A4 step 3, splitting the `=== 전사본 ===` tail out of `INSTRUCTION`) is a concrete instruction with the exact resulting expression. ✓

**Type consistency:** `MeetingMeta`, `RecordingSummary.meta`, `RecordingDetail.meta`, `uploadRecording(blob,{title?,meta?})`, `patchRecording(id,{title?,meta?})`, `attendeesCount`, `groupSegments`, `statusLabel` labels (대기/전사중/완료/실패) are used identically across tasks and match the backend payloads from Phase A. ✓

---

## Execution Handoff

(Filled in by the writing-plans skill conversation after save.)
