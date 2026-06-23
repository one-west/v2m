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
