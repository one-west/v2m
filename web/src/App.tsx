import { useState } from "react";
import { MeetingForm } from "./features/meeting/MeetingForm";
import { RecorderPanel } from "./features/recorder/RecorderPanel";
import { RecordingList } from "./features/recordings/RecordingList";
import { RecordingDetail } from "./features/recordings/RecordingDetail";
import { useRecordings } from "./hooks/useRecordings";
import { deleteRecording } from "./lib/api";
import type { MeetingMeta } from "./lib/types";

export function App() {
  const { recordings, loading, error, refresh } = useRecordings();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [draftMeta, setDraftMeta] = useState<MeetingMeta>({});
  const [draftLanguage, setDraftLanguage] = useState("ko");

  async function handleDelete(id: string) {
    await deleteRecording(id);
    if (selectedId === id) setSelectedId(null);
    refresh();
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
                onUploaded={handleUploaded} />
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
