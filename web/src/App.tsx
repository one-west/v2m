import { useEffect, useState } from "react";
import { MeetingForm } from "./features/meeting/MeetingForm";
import { RecorderPanel } from "./features/recorder/RecorderPanel";
import { RecordingList } from "./features/recordings/RecordingList";
import { RecordingDetail } from "./features/recordings/RecordingDetail";
import { useRecordings } from "./hooks/useRecordings";
import { deleteRecording, uploadRecording } from "./lib/api";
import { clearSession, getPendingSession, type PendingSession } from "./lib/recordingStore";
import type { MeetingMeta } from "./lib/types";

export function App() {
  const { recordings, loading, error, refresh } = useRecordings();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [draftMeta, setDraftMeta] = useState<MeetingMeta>({});
  const [draftLanguage, setDraftLanguage] = useState("ko");
  const [recording, setRecording] = useState(false);
  const [pending, setPending] = useState<PendingSession | null>(null);
  const [recovering, setRecovering] = useState(false);

  // On load (e.g. after a sleep/refresh that dropped an in-progress recording),
  // surface any buffered recording so it can be recovered instead of lost.
  useEffect(() => {
    getPendingSession().then(setPending).catch(() => {});
  }, []);

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

  function handleSelect(id: string) {
    // Leaving the recorder view mid-recording unmounts it and loses the audio.
    if (recording && !window.confirm("녹음 중입니다. 페이지를 이동하면 진행 중인 녹음이 사라집니다. 이동할까요?")) {
      return;
    }
    setSelectedId(id);
  }

  function handleUploaded() {
    setDraftTitle("");
    setDraftMeta({});
    setDraftLanguage("ko");
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
          <RecordingDetail id={selectedId}
            onBack={() => { setSelectedId(null); refresh(); }} />
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
              <RecorderPanel title={draftTitle} meta={draftMeta} language={draftLanguage}
                onUploaded={handleUploaded} onRecordingChange={setRecording} />
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
                <RecordingList recordings={recordings} onSelect={handleSelect} onDelete={handleDelete} />
              )}
            </div>
          </>
        )}
      </main>
    </>
  );
}
