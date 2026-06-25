import { useEffect, useState } from "react";
import { MeetingForm } from "./features/meeting/MeetingForm";
import { RecorderPanel } from "./features/recorder/RecorderPanel";
import { RecordingList } from "./features/recordings/RecordingList";
import { RecordingDetail } from "./features/recordings/RecordingDetail";
import { useRecordings } from "./hooks/useRecordings";
import { useRecorder } from "./hooks/useRecorder";
import { useBeforeUnloadGuard } from "./hooks/useBeforeUnloadGuard";
import { deleteRecording, uploadRecording } from "./lib/api";
import { appendChunk, beginSession, clearSession, getPendingSession, type PendingSession } from "./lib/recordingStore";
import { msToMmss } from "./lib/format";
import type { MeetingMeta } from "./lib/types";

export function App() {
  const { recordings, loading, error, refresh } = useRecordings();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [draftMeta, setDraftMeta] = useState<MeetingMeta>({});
  const [draftLanguage, setDraftLanguage] = useState("ko");
  const [pending, setPending] = useState<PendingSession | null>(null);
  const [recovering, setRecovering] = useState(false);

  // The recorder lives in App (not RecorderPanel) so it keeps running while the
  // user navigates between views inside the tab — MediaRecorder isn't unmounted.
  const { isRecording, elapsedMs, start, stop } = useRecorder({
    onChunk: (blob) => { appendChunk(blob).catch(() => {}); },
  });
  const [busy, setBusy] = useState(false);
  const [recError, setRecError] = useState<string | null>(null);
  useBeforeUnloadGuard(isRecording || busy);

  // On load, surface any recording buffered before a sleep/refresh dropped the tab.
  useEffect(() => {
    getPendingSession().then(setPending).catch(() => {});
  }, []);

  async function handleStart() {
    setRecError(null);
    try {
      await beginSession({ title: draftTitle, meta: draftMeta, language: draftLanguage }).catch(() => {});
      await start();
    } catch {
      setRecError("마이크 권한이 필요합니다.");
    }
  }

  async function handleStop() {
    setBusy(true);
    setRecError(null);
    try {
      const blob = await stop();
      await uploadRecording(blob, { title: draftTitle, meta: draftMeta, language: draftLanguage });
      await clearSession().catch(() => {});
      setDraftTitle("");
      setDraftMeta({});
      setDraftLanguage("ko");
      refresh();
    } catch {
      setRecError("업로드에 실패했습니다.");
    } finally {
      setBusy(false);
    }
  }

  async function handleRecover() {
    if (!pending) return;
    setRecovering(true);
    try {
      await uploadRecording(pending.audio, {
        title: pending.meta.title,
        meta: pending.meta.meta,
        language: pending.meta.language,
      });
      await clearSession().catch(() => {});
      setPending(null);
      refresh();
    } finally {
      setRecovering(false);
    }
  }

  async function handleDiscardPending() {
    await clearSession().catch(() => {});
    setPending(null);
  }

  async function handleDelete(id: string) {
    await deleteRecording(id);
    if (selectedId === id) setSelectedId(null);
    refresh();
  }

  return (
    <>
      <header className="topbar">
        <span className="logo">V</span>
        <h1 className="wordmark">V2M</h1>
        <span className="tagline">음성에서 회의록까지</span>
        {isRecording && selectedId && (
          <span className="rec-indicator">
            <span className="rec-dot" aria-hidden="true" />
            <span className="num">{msToMmss(elapsedMs)}</span>
            <button className="btn btn-secondary" onClick={handleStop} disabled={busy}>정지</button>
          </span>
        )}
      </header>
      <main className="container">
        {pending && (
          <div className="card" role="alert">
            <h2>중단된 녹음 발견</h2>
            <p className="sub">
              이전 녹음이 업로드 전에 중단되었습니다{pending.meta.title ? ` (${pending.meta.title})` : ""}.
              복구해서 전사를 진행할 수 있어요.
            </p>
            <div className="btn-group">
              <button className="btn btn-primary" onClick={handleRecover} disabled={recovering}>
                {recovering ? "복구 중…" : "복구"}
              </button>
              <button className="btn btn-danger-ghost" onClick={handleDiscardPending} disabled={recovering}>
                삭제
              </button>
            </div>
          </div>
        )}
        {selectedId ? (
          <RecordingDetail id={selectedId} onBack={() => { setSelectedId(null); refresh(); }} />
        ) : (
          <>
            <div className="card">
              <h2>새 회의</h2>
              <MeetingForm title={draftTitle} meta={draftMeta}
                onChange={(next) => { setDraftTitle(next.title); setDraftMeta(next.meta); }} />
              <div className="field" style={{ marginTop: 14, maxWidth: 220 }}>
                <label htmlFor="rec-lang">전사 언어</label>
                <select id="rec-lang" value={draftLanguage}
                  onChange={(e) => setDraftLanguage(e.target.value)}>
                  <option value="ko">한국어</option>
                  <option value="en">English</option>
                  <option value="auto">자동 감지</option>
                </select>
              </div>
              <RecorderPanel isRecording={isRecording} elapsedMs={elapsedMs} busy={busy}
                error={recError} onStart={handleStart} onStop={handleStop} />
            </div>
            <div className="card">
              <h2>회의 목록</h2>
              {error ? (
                <p role="alert" className="warn-text">
                  목록을 불러오지 못했습니다. 백엔드 서버가 실행 중인지 확인해 주세요.
                </p>
              ) : loading && recordings.length === 0 ? (
                <p className="empty">불러오는 중…</p>
              ) : (
                <RecordingList recordings={recordings} onSelect={setSelectedId} onDelete={handleDelete} />
              )}
            </div>
          </>
        )}
      </main>
    </>
  );
}
