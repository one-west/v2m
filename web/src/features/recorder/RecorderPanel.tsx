import { useEffect, useState } from "react";
import { useRecorder } from "../../hooks/useRecorder";
import { useBeforeUnloadGuard } from "../../hooks/useBeforeUnloadGuard";
import { uploadRecording } from "../../lib/api";
import { msToMmss } from "../../lib/format";
import { appendChunk, beginSession, clearSession } from "../../lib/recordingStore";
import type { MeetingMeta } from "../../lib/types";

interface Props {
  title: string;
  meta: MeetingMeta;
  language: string;
  onUploaded: () => void;
  onRecordingChange?: (recording: boolean) => void;
}

export function RecorderPanel({ title, meta, language, onUploaded, onRecordingChange }: Props) {
  // Persist each chunk to IndexedDB so the recording survives a reload (sleep/crash).
  const { isRecording, elapsedMs, start, stop } = useRecorder({
    onChunk: (blob) => { appendChunk(blob).catch(() => {}); },
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Warn before refresh / close / navigate while a recording is in progress or
  // its upload hasn't finished, so the in-memory audio isn't silently lost.
  const inProgress = isRecording || busy;
  useBeforeUnloadGuard(inProgress);
  useEffect(() => { onRecordingChange?.(isRecording); }, [isRecording, onRecordingChange]);

  async function handleStart() {
    setError(null);
    try {
      // Snapshot the meeting fields so a recovered recording uploads with them.
      await beginSession({ title, meta, language }).catch(() => {});
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
      await clearSession().catch(() => {}); // uploaded -> drop the durable buffer
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
