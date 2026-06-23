# V2M Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Vite + React + TypeScript browser UI that records meeting audio, uploads it to the local backend, shows the speaker-labeled timestamped transcript, and offers a one-click "copy transcript + prompt → open claude.ai" flow plus md/txt export.

**Architecture:** A small single-page React app (no router — view state is `selectedId | null`). A typed `lib/api.ts` wraps the backend `/api` contract with `fetch`; components consume it. Audio is captured with the `MediaRecorder` API via a `useRecorder` hook (webm/opus, 1s timeslice) and uploaded as a single Blob on stop. A `useRecordings` hook lists + polls. The minutes-formatting step is external: the app copies a prompt bundle to the clipboard and opens claude.ai — it never calls an LLM.

**Tech Stack:** Vite 5, React 18, TypeScript 5 (strict), Vitest 2 + @testing-library/react (jsdom). No state-management or router libraries (YAGNI).

## Global Constraints

- Vite + React + TypeScript only. `strict: true`. No router/state libraries.
- The app calls **relative `/api/...`** (and `/health`) — never an absolute host. Dev: Vite proxy to `http://127.0.0.1:8000`. Prod: same-origin (FastAPI serves `web/dist`).
- Backend `RecordingStatus` values are exactly `recorded | transcribing | done | failed`.
- **No in-app LLM / no minutes storage.** The "정형화" step is the user pasting into claude.ai. The app's job ends at transcript + copy-for-claude bundle + export.
- UI copy is Korean.
- Build output dir is `web/dist` (the backend mounts it at `/`).
- Audio capture: `audio/webm;codecs=opus` when supported (feature-detect with `MediaRecorder.isTypeSupported`); upload filename `recording.webm`, multipart field name `file`.
- Backend API contract (consumed, do not change):
  - `GET /api/recordings` → `{id,title,status,created_at,duration_sec}[]`
  - `POST /api/recordings` (multipart `file`, optional `title`) → `201 {id,title,status,created_at}`
  - `GET /api/recordings/{id}` → `{id,title,status,created_at,duration_sec,error,transcript}`
  - `GET /api/recordings/{id}/status` → `{id,status,error}`
  - `POST /api/recordings/{id}/retry` → `200`
  - `DELETE /api/recordings/{id}` → `204`
  - `GET /api/recordings/{id}/prompt` → `{prompt,transcript_text,char_count,too_long}`
  - `GET /api/recordings/{id}/export?format=md|txt` → file download
- TDD: failing test first, minimal implementation, frequent commits. DRY, YAGNI.

---

## File Structure

```
web/
  package.json
  tsconfig.json
  tsconfig.node.json
  vite.config.ts            # @vitejs/plugin-react, /api+/health proxy, vitest config
  index.html
  src/
    test-setup.ts           # @testing-library/jest-dom
    main.tsx                # React root
    App.tsx                 # layout + list/detail view switch
    styles.css              # minimal styling
    lib/
      types.ts              # RecordingStatus, RecordingSummary, RecordingDetail, Transcript, PromptBundle
      api.ts                # typed fetch wrappers
      api.test.ts
      format.ts             # msToMmss, statusLabel (Korean)
      format.test.ts
    hooks/
      useRecorder.ts        # MediaRecorder wrapper
      useRecorder.test.ts
      useRecordings.ts      # list + polling
      useRecordings.test.ts
    features/
      recorder/
        RecorderPanel.tsx
        RecorderPanel.test.tsx
      recordings/
        StatusBadge.tsx
        RecordingList.tsx
        RecordingList.test.tsx
        RecordingDetail.tsx
        RecordingDetail.test.tsx
        CopyForClaude.tsx
        CopyForClaude.test.tsx
    App.test.tsx
```

---

### Task 1: Scaffold Vite + React + TS + Vitest

**Files:**
- Create: `web/package.json`, `web/tsconfig.json`, `web/tsconfig.node.json`, `web/vite.config.ts`, `web/index.html`
- Create: `web/src/main.tsx`, `web/src/App.tsx`, `web/src/styles.css`, `web/src/test-setup.ts`, `web/src/lib/types.ts`
- Test: `web/src/App.test.tsx`

**Interfaces:**
- Produces:
  - `App` (named export) React component rendering an `<h1>V2M …</h1>`.
  - `lib/types.ts`: `RecordingStatus` (`"recorded"|"transcribing"|"done"|"failed"`), `RecordingSummary {id,title,status,created_at,duration_sec}`, `TranscriptSegment {speaker,start_ms,end_ms,text}`, `Transcript {segments,full_text,language}`, `RecordingDetail {id,title,status,created_at,duration_sec,error,transcript}`, `PromptBundle {prompt,transcript_text,char_count,too_long}`.
  - `npm test` runs Vitest; `npm run build` outputs `web/dist`.

**Environment setup (first task — bootstrap before tests run):**
Work from repo root. Create the `web/` files, then `cd web && npm install`. Run tests with `npm test`. Add `web/.gitignore` (`node_modules/`, `dist/`) — authorized scaffolding. Do not commit `node_modules/` or `dist/`.

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

- [ ] **Step 3: Create index.html, entry, styles, test setup, types**

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

`web/src/styles.css`:

```css
:root { font-family: system-ui, sans-serif; }
.app { max-width: 720px; margin: 0 auto; padding: 1.5rem; }
.badge { padding: 0.1rem 0.5rem; border-radius: 0.5rem; font-size: 0.8rem; }
.badge-done { background: #d1fae5; }
.badge-failed { background: #fee2e2; }
.badge-transcribing, .badge-recorded { background: #e0e7ff; }
.recording-list { list-style: none; padding: 0; }
.recording-list li { display: flex; gap: 0.75rem; align-items: center; padding: 0.5rem 0; }
.transcript .seg { margin-bottom: 0.75rem; }
.transcript .head { font-weight: 600; color: #4338ca; }
```

`web/src/lib/types.ts`:

```ts
export type RecordingStatus = "recorded" | "transcribing" | "done" | "failed";

export interface RecordingSummary {
  id: string;
  title: string;
  status: RecordingStatus;
  created_at: string;
  duration_sec: number | null;
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
}

export interface PromptBundle {
  prompt: string;
  transcript_text: string;
  char_count: number;
  too_long: boolean;
}
```

- [ ] **Step 4: Write the failing test**

`web/src/App.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { App } from "./App";

describe("App", () => {
  it("renders the app heading", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /V2M/ })).toBeInTheDocument();
  });
});
```

- [ ] **Step 5: Run install + test to verify it fails**

Run: `cd web && npm install && npm test`
Expected: FAIL — `App.tsx` does not exist / no default content.

- [ ] **Step 6: Create minimal entry + App**

`web/src/App.tsx`:

```tsx
export function App() {
  return (
    <main className="app">
      <h1>V2M — 음성에서 회의록까지</h1>
    </main>
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

- [ ] **Step 7: Run test to verify it passes**

Run: `cd web && npm test`
Expected: PASS (1 passed)

- [ ] **Step 8: Verify build works**

Run: `cd web && npm run build`
Expected: succeeds, creates `web/dist/index.html`.

- [ ] **Step 9: Commit**

```bash
git add web/package.json web/tsconfig.json web/tsconfig.node.json web/vite.config.ts web/index.html web/.gitignore web/src/main.tsx web/src/App.tsx web/src/styles.css web/src/test-setup.ts web/src/lib/types.ts web/src/App.test.tsx
git commit -m "feat(web): scaffold Vite+React+TS+Vitest, shared types"
```

---

### Task 2: API client + format helpers

**Files:**
- Create: `web/src/lib/api.ts`, `web/src/lib/format.ts`
- Test: `web/src/lib/api.test.ts`, `web/src/lib/format.test.ts`

**Interfaces:**
- Consumes: `lib/types.ts`.
- Produces (`lib/api.ts`):
  - `listRecordings(): Promise<RecordingSummary[]>`
  - `getRecording(id: string): Promise<RecordingDetail>`
  - `uploadRecording(blob: Blob, title?: string): Promise<RecordingSummary>`
  - `retryRecording(id: string): Promise<void>`
  - `deleteRecording(id: string): Promise<void>`
  - `getPrompt(id: string): Promise<PromptBundle>`
  - `exportUrl(id: string, format: "md" | "txt"): string`
- Produces (`lib/format.ts`):
  - `msToMmss(ms: number): string` (e.g. `65000 → "01:05"`)
  - `statusLabel(status: RecordingStatus): string` (Korean)

- [ ] **Step 1: Write the failing format test**

`web/src/lib/format.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { msToMmss, statusLabel } from "./format";

describe("format", () => {
  it("formats ms as mm:ss", () => {
    expect(msToMmss(0)).toBe("00:00");
    expect(msToMmss(65000)).toBe("01:05");
    expect(msToMmss(3599000)).toBe("59:59");
  });

  it("maps status to Korean labels", () => {
    expect(statusLabel("recorded")).toBe("대기 중");
    expect(statusLabel("transcribing")).toBe("전사 중");
    expect(statusLabel("done")).toBe("완료");
    expect(statusLabel("failed")).toBe("실패");
  });
});
```

- [ ] **Step 2: Write the failing api test**

`web/src/lib/api.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import * as api from "./api";

function mockFetch(body: unknown, ok = true, status = 200) {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    json: () => Promise.resolve(body),
  });
}

beforeEach(() => {
  vi.stubGlobal("fetch", mockFetch([]));
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api", () => {
  it("listRecordings GETs /api/recordings", async () => {
    const f = mockFetch([{ id: "1" }]);
    vi.stubGlobal("fetch", f);
    const rows = await api.listRecordings();
    expect(f).toHaveBeenCalledWith("/api/recordings");
    expect(rows).toEqual([{ id: "1" }]);
  });

  it("uploadRecording POSTs multipart with file and title", async () => {
    const f = mockFetch({ id: "1", title: "T", status: "recorded", created_at: "x" }, true, 201);
    vi.stubGlobal("fetch", f);
    await api.uploadRecording(new Blob(["a"]), "T");
    const [url, opts] = f.mock.calls[0];
    expect(url).toBe("/api/recordings");
    expect(opts.method).toBe("POST");
    expect(opts.body).toBeInstanceOf(FormData);
    expect((opts.body as FormData).get("title")).toBe("T");
    expect((opts.body as FormData).get("file")).toBeInstanceOf(File);
  });

  it("retryRecording POSTs retry", async () => {
    const f = mockFetch({}, true, 200);
    vi.stubGlobal("fetch", f);
    await api.retryRecording("1");
    expect(f).toHaveBeenCalledWith("/api/recordings/1/retry", { method: "POST" });
  });

  it("deleteRecording tolerates 204", async () => {
    const f = mockFetch(null, false, 204);
    vi.stubGlobal("fetch", f);
    await expect(api.deleteRecording("1")).resolves.toBeUndefined();
  });

  it("throws on non-ok json response", async () => {
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
import type { RecordingStatus } from "./types";

export function msToMmss(ms: number): string {
  const total = Math.floor(ms / 1000);
  const m = String(Math.floor(total / 60)).padStart(2, "0");
  const s = String(total % 60).padStart(2, "0");
  return `${m}:${s}`;
}

const STATUS_LABELS: Record<RecordingStatus, string> = {
  recorded: "대기 중",
  transcribing: "전사 중",
  done: "완료",
  failed: "실패",
};

export function statusLabel(status: RecordingStatus): string {
  return STATUS_LABELS[status];
}
```

- [ ] **Step 5: Implement api**

`web/src/lib/api.ts`:

```ts
import type { PromptBundle, RecordingDetail, RecordingSummary } from "./types";

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

export async function uploadRecording(blob: Blob, title?: string): Promise<RecordingSummary> {
  const form = new FormData();
  form.append("file", new File([blob], "recording.webm", { type: blob.type || "audio/webm" }));
  if (title) form.append("title", title);
  return jsonOrThrow(await fetch("/api/recordings", { method: "POST", body: form }));
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
Expected: PASS (format 2 + api 6)

- [ ] **Step 7: Commit**

```bash
git add web/src/lib/api.ts web/src/lib/format.ts web/src/lib/api.test.ts web/src/lib/format.test.ts
git commit -m "feat(web): typed API client + format helpers"
```

---

### Task 3: useRecorder hook (MediaRecorder)

**Files:**
- Create: `web/src/hooks/useRecorder.ts`
- Test: `web/src/hooks/useRecorder.test.ts`

**Interfaces:**
- Produces:
  - `useRecorder(): { isRecording: boolean; elapsedMs: number; start(): Promise<void>; stop(): Promise<Blob> }`.
  - `start()` calls `navigator.mediaDevices.getUserMedia({audio:true})`, creates a `MediaRecorder` (opus when `isTypeSupported`), starts with a 1s timeslice, accumulates `dataavailable` chunks, runs an elapsed timer.
  - `stop()` resolves to the assembled `Blob`, stops tracks, clears the timer.

- [ ] **Step 1: Write the failing test**

`web/src/hooks/useRecorder.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useRecorder } from "./useRecorder";

class FakeMediaRecorder {
  static isTypeSupported() {
    return true;
  }
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  mimeType = "audio/webm;codecs=opus";
  state = "inactive";
  constructor(public stream: { getTracks: () => { stop: () => void }[] }) {}
  start() {
    this.state = "recording";
    this.ondataavailable?.({ data: new Blob(["chunk"], { type: this.mimeType }) });
  }
  stop() {
    this.state = "inactive";
    this.onstop?.();
  }
}

beforeEach(() => {
  vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
  vi.stubGlobal("navigator", {
    mediaDevices: {
      getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] }),
    },
  });
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useRecorder", () => {
  it("records then returns a blob on stop", async () => {
    const { result } = renderHook(() => useRecorder());
    await act(async () => {
      await result.current.start();
    });
    expect(result.current.isRecording).toBe(true);

    let blob: Blob = new Blob();
    await act(async () => {
      blob = await result.current.stop();
    });
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
    rec.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };
    rec.start(1000);
    recorderRef.current = rec;
    startedAtRef.current = Date.now();
    setElapsedMs(0);
    setIsRecording(true);
    timerRef.current = window.setInterval(() => {
      setElapsedMs(Date.now() - startedAtRef.current);
    }, 250);
  }, []);

  const stop = useCallback(() => {
    return new Promise<Blob>((resolve) => {
      const rec = recorderRef.current;
      if (!rec) {
        resolve(new Blob());
        return;
      }
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
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add web/src/hooks/useRecorder.ts web/src/hooks/useRecorder.test.ts
git commit -m "feat(web): useRecorder MediaRecorder hook"
```

---

### Task 4: RecorderPanel component

**Files:**
- Create: `web/src/features/recorder/RecorderPanel.tsx`
- Test: `web/src/features/recorder/RecorderPanel.test.tsx`

**Interfaces:**
- Consumes: `useRecorder`, `api.uploadRecording`, `format.msToMmss`.
- Produces: `RecorderPanel({ onUploaded }: { onUploaded: () => void })`. Shows the elapsed timer and a 녹음 시작 / 녹음 정지 toggle. On stop, assembles the blob, uploads it, calls `onUploaded`. Shows a mic-permission error on `start()` failure.

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

beforeEach(() => {
  vi.clearAllMocks();
  recorderState.isRecording = false;
});

describe("RecorderPanel", () => {
  it("starts recording on click", async () => {
    render(<RecorderPanel onUploaded={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "녹음 시작" }));
    expect(startMock).toHaveBeenCalled();
  });

  it("uploads and notifies on stop", async () => {
    recorderState.isRecording = true;
    const onUploaded = vi.fn();
    render(<RecorderPanel onUploaded={onUploaded} />);
    await userEvent.click(screen.getByRole("button", { name: "녹음 정지" }));
    await waitFor(() => expect(uploadRecording).toHaveBeenCalled());
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

export function RecorderPanel({ onUploaded }: { onUploaded: () => void }) {
  const { isRecording, elapsedMs, start, stop } = useRecorder();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleStart() {
    setError(null);
    try {
      await start();
    } catch {
      setError("마이크 권한이 필요합니다.");
    }
  }

  async function handleStop() {
    setBusy(true);
    setError(null);
    try {
      const blob = await stop();
      await uploadRecording(blob);
      onUploaded();
    } catch {
      setError("업로드에 실패했습니다.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="recorder">
      <span className="timer">{msToMmss(elapsedMs)}</span>
      {!isRecording ? (
        <button onClick={handleStart} disabled={busy}>녹음 시작</button>
      ) : (
        <button onClick={handleStop} disabled={busy}>녹음 정지</button>
      )}
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm test -- src/features/recorder`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add web/src/features/recorder/RecorderPanel.tsx web/src/features/recorder/RecorderPanel.test.tsx
git commit -m "feat(web): RecorderPanel record + upload"
```

---

### Task 5: StatusBadge + RecordingList

**Files:**
- Create: `web/src/features/recordings/StatusBadge.tsx`, `web/src/features/recordings/RecordingList.tsx`
- Test: `web/src/features/recordings/RecordingList.test.tsx`

**Interfaces:**
- Consumes: `types.RecordingSummary/RecordingStatus`, `format.statusLabel`.
- Produces:
  - `StatusBadge({ status }: { status: RecordingStatus })` → `<span class="badge badge-<status>">{statusLabel}</span>`.
  - `RecordingList({ recordings, onSelect, onDelete })` where `onSelect: (id) => void`, `onDelete: (id) => void`. Empty state shows "아직 녹음이 없습니다." Each row: title button (select), status badge, delete button (`aria-label` = `<title> 삭제`).

- [ ] **Step 1: Write the failing test**

`web/src/features/recordings/RecordingList.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RecordingList } from "./RecordingList";
import type { RecordingSummary } from "../../lib/types";

const rows: RecordingSummary[] = [
  { id: "a", title: "주간회의", status: "done", created_at: "2026-06-22T01:00:00", duration_sec: 60 },
  { id: "b", title: "스프린트", status: "transcribing", created_at: "2026-06-22T02:00:00", duration_sec: null },
];

describe("RecordingList", () => {
  it("shows empty state", () => {
    render(<RecordingList recordings={[]} onSelect={vi.fn()} onDelete={vi.fn()} />);
    expect(screen.getByText("아직 녹음이 없습니다.")).toBeInTheDocument();
  });

  it("renders rows with status labels and fires select/delete", async () => {
    const onSelect = vi.fn();
    const onDelete = vi.fn();
    render(<RecordingList recordings={rows} onSelect={onSelect} onDelete={onDelete} />);
    expect(screen.getByText("완료")).toBeInTheDocument();
    expect(screen.getByText("전사 중")).toBeInTheDocument();

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
import { StatusBadge } from "./StatusBadge";

export function RecordingList({
  recordings,
  onSelect,
  onDelete,
}: {
  recordings: RecordingSummary[];
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  if (recordings.length === 0) {
    return <p className="empty">아직 녹음이 없습니다.</p>;
  }
  return (
    <ul className="recording-list">
      {recordings.map((r) => (
        <li key={r.id}>
          <button className="title" onClick={() => onSelect(r.id)}>{r.title}</button>
          <StatusBadge status={r.status} />
          <button className="delete" aria-label={`${r.title} 삭제`} onClick={() => onDelete(r.id)}>
            삭제
          </button>
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd web && npm test -- src/features/recordings/RecordingList`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add web/src/features/recordings/StatusBadge.tsx web/src/features/recordings/RecordingList.tsx web/src/features/recordings/RecordingList.test.tsx
git commit -m "feat(web): StatusBadge + RecordingList"
```

---

### Task 6: useRecordings hook (list + polling)

**Files:**
- Create: `web/src/hooks/useRecordings.ts`
- Test: `web/src/hooks/useRecordings.test.ts`

**Interfaces:**
- Consumes: `api.listRecordings`, `types.RecordingSummary`.
- Produces: `useRecordings(): { recordings: RecordingSummary[]; loading: boolean; refresh(): Promise<RecordingSummary[]> }`. On mount it loads the list and schedules a poll (3s while any recording is `recorded`/`transcribing`, else 12s). `refresh()` re-fetches immediately.

- [ ] **Step 1: Write the failing test**

`web/src/hooks/useRecordings.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";

vi.mock("../lib/api", () => ({ listRecordings: vi.fn() }));
import { listRecordings } from "../lib/api";
import { useRecordings } from "./useRecordings";

const sample = [{ id: "a", title: "T", status: "done", created_at: "x", duration_sec: null }];

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
    await act(async () => {
      await result.current.refresh();
    });
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
    return () => {
      active = false;
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
  }, [refresh]);

  return { recordings, loading, refresh };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm test -- src/hooks/useRecordings`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add web/src/hooks/useRecordings.ts web/src/hooks/useRecordings.test.ts
git commit -m "feat(web): useRecordings list + polling hook"
```

---

### Task 7: RecordingDetail (transcript view + retry + export)

**Files:**
- Create: `web/src/features/recordings/RecordingDetail.tsx`
- Test: `web/src/features/recordings/RecordingDetail.test.tsx`

**Interfaces:**
- Consumes: `api.getRecording`, `api.retryRecording`, `api.exportUrl`, `format.msToMmss/statusLabel`, `StatusBadge`, `CopyForClaude` (created in Task 8 — import it; this task adds a temporary stub if Task 8 not done — see note).
- Produces:
  - `groupSegments(segments: TranscriptSegment[]): { speaker: string; startMs: number; lines: string[] }[]` (exported pure function — merges consecutive same-speaker segments).
  - `RecordingDetail({ id, onBack }: { id: string; onBack: () => void })`. Loads detail; when `done`, renders `CopyForClaude`, export links, and the grouped transcript; when `failed`, shows error + 다시 시도 (retry then reload); when `recorded`/`transcribing`, shows a waiting message.

> Dependency note: this task imports `CopyForClaude` from Task 8. Implement Task 8 first, OR temporarily create `CopyForClaude.tsx` returning `null` and replace it in Task 8. The plan orders Task 8 right after; if executing in order, create a minimal `CopyForClaude` stub here and the real one in Task 8. To avoid a throwaway, **execute Task 8 before Task 7's transcript-render step** is acceptable. Simplest: this task's test mocks `./CopyForClaude`.

- [ ] **Step 1: Write the failing test**

`web/src/features/recordings/RecordingDetail.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RecordingDetail, groupSegments } from "./RecordingDetail";

vi.mock("../../lib/api", () => ({
  getRecording: vi.fn(),
  retryRecording: vi.fn().mockResolvedValue(undefined),
  exportUrl: (id: string, f: string) => `/api/recordings/${id}/export?format=${f}`,
}));
vi.mock("./CopyForClaude", () => ({ CopyForClaude: () => <div>copy-stub</div> }));
import { getRecording, retryRecording } from "../../lib/api";

const doneDetail = {
  id: "a", title: "주간회의", status: "done", created_at: "x", duration_sec: 60, error: null,
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
  it("renders grouped transcript when done", async () => {
    (getRecording as ReturnType<typeof vi.fn>).mockResolvedValue(doneDetail);
    render(<RecordingDetail id="a" onBack={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("안녕하세요")).toBeInTheDocument());
    expect(screen.getByText(/\[00:00\] SPEAKER_00/)).toBeInTheDocument();
    expect(screen.getByText(/\[01:05\] SPEAKER_01/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Markdown/ })).toHaveAttribute(
      "href", "/api/recordings/a/export?format=md",
    );
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
import { exportUrl, getRecording, retryRecording } from "../../lib/api";
import type { RecordingDetail as Detail, TranscriptSegment } from "../../lib/types";
import { msToMmss, statusLabel } from "../../lib/format";
import { StatusBadge } from "./StatusBadge";
import { CopyForClaude } from "./CopyForClaude";

interface Group {
  speaker: string;
  startMs: number;
  lines: string[];
}

export function groupSegments(segments: TranscriptSegment[]): Group[] {
  const groups: Group[] = [];
  for (const seg of segments) {
    const last = groups[groups.length - 1];
    if (last && last.speaker === seg.speaker) {
      last.lines.push(seg.text);
    } else {
      groups.push({ speaker: seg.speaker, startMs: seg.start_ms, lines: [seg.text] });
    }
  }
  return groups;
}

export function RecordingDetail({ id, onBack }: { id: string; onBack: () => void }) {
  const [detail, setDetail] = useState<Detail | null>(null);

  async function load() {
    setDetail(await getRecording(id));
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (!detail) return <p>불러오는 중…</p>;

  return (
    <div className="detail">
      <button onClick={onBack}>← 목록</button>
      <h2>{detail.title}</h2>
      <StatusBadge status={detail.status} />

      {detail.status === "failed" && (
        <div role="alert">
          <p>전사 실패: {detail.error}</p>
          <button
            onClick={async () => {
              await retryRecording(id);
              load();
            }}
          >
            다시 시도
          </button>
        </div>
      )}

      {detail.status === "done" && detail.transcript && (
        <>
          <CopyForClaude id={id} />
          <div className="export">
            <a href={exportUrl(id, "md")}>Markdown 내보내기</a>
            <a href={exportUrl(id, "txt")}>TXT 내보내기</a>
          </div>
          <div className="transcript">
            {groupSegments(detail.transcript.segments).map((g, i) => (
              <div className="seg" key={i}>
                <div className="head">
                  [{msToMmss(g.startMs)}] {g.speaker}
                </div>
                {g.lines.map((line, j) => (
                  <p key={j}>{line}</p>
                ))}
              </div>
            ))}
          </div>
        </>
      )}

      {(detail.status === "recorded" || detail.status === "transcribing") && (
        <p>{statusLabel(detail.status)}… 잠시만 기다려 주세요.</p>
      )}
    </div>
  );
}
```

> The transcript header text node is split as `[00:00] ` + `SPEAKER_00`. The test matches it with a regex on the parent; React renders both in the same `.head` div so `getByText(/\[00:00\] SPEAKER_00/)` resolves via normalized text. If RTL splits the match, use `screen.getByText((_, el) => el?.textContent === "[00:00] SPEAKER_00")` — but the single-div layout above keeps them in one node's textContent.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm test -- src/features/recordings/RecordingDetail`
Expected: PASS (groupSegments 1 + RecordingDetail 2)

- [ ] **Step 5: Commit**

```bash
git add web/src/features/recordings/RecordingDetail.tsx web/src/features/recordings/RecordingDetail.test.tsx
git commit -m "feat(web): RecordingDetail transcript view + retry + export"
```

---

### Task 8: CopyForClaude component

**Files:**
- Create: `web/src/features/recordings/CopyForClaude.tsx`
- Test: `web/src/features/recordings/CopyForClaude.test.tsx`

**Interfaces:**
- Consumes: `api.getPrompt`.
- Produces: `CopyForClaude({ id }: { id: string })`. On button click: fetches the prompt bundle, writes `bundle.prompt` to the clipboard, opens `https://claude.ai/new` in a new tab, shows a confirmation with the char count, and — if `bundle.too_long` — a warning to split the paste.

> If a temporary stub `CopyForClaude.tsx` was created during Task 7, replace it entirely with this implementation.

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

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("navigator", { clipboard: { writeText } });
  vi.stubGlobal("open", vi.fn());
});

describe("CopyForClaude", () => {
  it("copies the prompt and confirms", async () => {
    (getPrompt as ReturnType<typeof vi.fn>).mockResolvedValue({
      prompt: "PROMPT-TEXT", transcript_text: "t", char_count: 12, too_long: false,
    });
    render(<CopyForClaude id="a" />);
    await userEvent.click(screen.getByRole("button", { name: /복사/ }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("PROMPT-TEXT"));
    expect(screen.getByRole("status")).toHaveTextContent(/복사되었습니다/);
    expect(window.open).toHaveBeenCalledWith("https://claude.ai/new", "_blank", "noopener");
  });

  it("warns when too long", async () => {
    (getPrompt as ReturnType<typeof vi.fn>).mockResolvedValue({
      prompt: "x", transcript_text: "t", char_count: 99999, too_long: true,
    });
    render(<CopyForClaude id="a" />);
    await userEvent.click(screen.getByRole("button", { name: /복사/ }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/한도/));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test -- src/features/recordings/CopyForClaude`
Expected: FAIL — component not found (or stub returns null).

- [ ] **Step 3: Implement the component**

`web/src/features/recordings/CopyForClaude.tsx`:

```tsx
import { useState } from "react";
import { getPrompt } from "../../lib/api";

const CLAUDE_URL = "https://claude.ai/new";

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
      window.open(CLAUDE_URL, "_blank", "noopener");
    } catch {
      setState("error");
    }
  }

  return (
    <div className="copy-for-claude">
      <button onClick={handleCopy}>전사본 + 프롬프트 복사 후 claude.ai 열기</button>
      {state === "copied" && (
        <p role="status">
          복사되었습니다. claude.ai에 붙여넣으세요.
          {charCount !== null && ` (${charCount.toLocaleString()}자)`}
        </p>
      )}
      {tooLong && (
        <p role="alert">전사본이 길어 claude.ai 입력 한도를 넘을 수 있습니다. 나눠서 붙여넣으세요.</p>
      )}
      {state === "error" && <p role="alert">복사에 실패했습니다.</p>}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm test -- src/features/recordings/CopyForClaude`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add web/src/features/recordings/CopyForClaude.tsx web/src/features/recordings/CopyForClaude.test.tsx
git commit -m "feat(web): CopyForClaude prompt copy + claude.ai open"
```

---

### Task 9: App integration + build verification

**Files:**
- Modify: `web/src/App.tsx`
- Modify: `web/src/App.test.tsx` (replace the Task 1 smoke test)
- Test: `web/src/App.test.tsx`

**Interfaces:**
- Consumes: `useRecordings`, `api.deleteRecording`, `RecorderPanel`, `RecordingList`, `RecordingDetail`.
- Produces: `App` wires the recorder + list (default view) and switches to `RecordingDetail` when a recording is selected; deleting refreshes the list; `onBack` returns to the list and refreshes.

- [ ] **Step 1: Write the failing test**

Replace `web/src/App.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";

vi.mock("./lib/api", () => ({
  listRecordings: vi.fn().mockResolvedValue([
    { id: "a", title: "주간회의", status: "done", created_at: "x", duration_sec: 1 },
  ]),
  deleteRecording: vi.fn().mockResolvedValue(undefined),
  getRecording: vi.fn().mockResolvedValue({
    id: "a", title: "주간회의", status: "done", created_at: "x", duration_sec: 1, error: null,
    transcript: { segments: [{ speaker: "SPEAKER_00", start_ms: 0, end_ms: 1000, text: "안녕" }], full_text: "안녕", language: "ko" },
  }),
}));
vi.mock("./hooks/useRecorder", () => ({
  useRecorder: () => ({ isRecording: false, elapsedMs: 0, start: vi.fn(), stop: vi.fn() }),
}));
vi.mock("./features/recordings/CopyForClaude", () => ({ CopyForClaude: () => <div>copy</div> }));

beforeEach(() => vi.clearAllMocks());

describe("App", () => {
  it("shows recorder + list, then opens detail on select", async () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /V2M/ })).toBeInTheDocument();
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
Expected: FAIL — App still renders only the heading.

- [ ] **Step 3: Implement App**

Replace `web/src/App.tsx`:

```tsx
import { useState } from "react";
import { RecorderPanel } from "./features/recorder/RecorderPanel";
import { RecordingList } from "./features/recordings/RecordingList";
import { RecordingDetail } from "./features/recordings/RecordingDetail";
import { useRecordings } from "./hooks/useRecordings";
import { deleteRecording } from "./lib/api";

export function App() {
  const { recordings, refresh } = useRecordings();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  async function handleDelete(id: string) {
    await deleteRecording(id);
    if (selectedId === id) setSelectedId(null);
    refresh();
  }

  return (
    <main className="app">
      <h1>V2M — 음성에서 회의록까지</h1>
      {selectedId ? (
        <RecordingDetail
          id={selectedId}
          onBack={() => {
            setSelectedId(null);
            refresh();
          }}
        />
      ) : (
        <>
          <RecorderPanel onUploaded={refresh} />
          <RecordingList recordings={recordings} onSelect={setSelectedId} onDelete={handleDelete} />
        </>
      )}
    </main>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm test -- src/App`
Expected: PASS (1 passed)

- [ ] **Step 5: Run the full suite + build**

Run: `cd web && npm test && npm run build`
Expected: all tests PASS; `web/dist/index.html` produced (the backend serves this at `/`).

- [ ] **Step 6: Commit**

```bash
git add web/src/App.tsx web/src/App.test.tsx
git commit -m "feat(web): wire recorder, list, and detail into App"
```

---

## Self-Review

**Spec coverage (frontend portions of `v2m-voice-to-minutes-design.md`):**
- Browser recording (MediaRecorder, webm/opus, timeslice) → Tasks 3, 4. ✓
- Upload to local backend → Tasks 2, 4. ✓
- Recording list + status + polling → Tasks 5, 6. ✓
- Speaker-grouped, timestamped transcript view → Task 7 (`groupSegments` + `[mm:ss] SPEAKER`). ✓
- Retry on failed → Task 7. ✓
- Copy-for-claude bundle (prompt + clipboard + open claude.ai + too-long warning) → Task 8. ✓
- Export md/txt → Task 7 (links to backend export endpoint). ✓
- Relative `/api`, Vite proxy in dev, `web/dist` served in prod → Task 1 config. ✓
- No in-app LLM / no minutes storage → enforced by design (only copy + open). ✓
- Korean UI copy → all components. ✓

**Deferred (documented, non-blocking for localhost single-user MVP):**
- **Playwright E2E** (spec §11 lists it): the full record→transcript→copy E2E needs a running backend with ffmpeg + WhisperX models, which is environment-heavy and flaky in CI. Component/hook tests (Vitest + Testing Library) cover the UI behavior — recorder, upload, list/poll, transcript render, retry, copy, app wiring. Add a route-mocked Playwright smoke in a later hardening pass.
- First-run model-download UI and a Settings page (HF token / model size) — backend §5.5 guardrails exist; the UI for them is a later task, not required for the core record→transcript→copy flow.

**Placeholder scan:** No TBD/TODO; every code step shows full code and exact commands. The Task 7 "dependency note" is resolved concretely (test mocks `./CopyForClaude`; Task 8 delivers the real one). ✓

**Type consistency:** `RecordingStatus`, `RecordingSummary`, `RecordingDetail`, `Transcript`, `PromptBundle`, `useRecorder().{isRecording,elapsedMs,start,stop}`, `useRecordings().{recordings,loading,refresh}`, `groupSegments`, `exportUrl(id,"md"|"txt")`, `getPrompt`, `uploadRecording(blob,title?)` are used identically across tasks and match the backend contract in Global Constraints. ✓

---

## Execution Handoff

(Filled in by the writing-plans skill conversation after save.)
