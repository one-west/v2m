import { useState } from "react";
import { useRecorder } from "../../hooks/useRecorder";
import { uploadRecording } from "../../lib/api";
import { msToMmss } from "../../lib/format";
import type { MeetingMeta } from "../../lib/types";

interface Props { title: string; meta: MeetingMeta; language: string; onUploaded: () => void; }

export function RecorderPanel({ title, meta, language, onUploaded }: Props) {
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
      await uploadRecording(blob, { title, meta, language });
      onUploaded();
    } catch {
      setError("업로드에 실패했습니다.");
    } finally {
      setBusy(false);
    }
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
