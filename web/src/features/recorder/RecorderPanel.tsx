import { msToMmss } from "../../lib/format";

interface Props {
  isRecording: boolean;
  elapsedMs: number;
  busy: boolean;
  error: string | null;
  onStart: () => void;
  onStop: () => void;
}

// Presentational only — the recorder lifecycle lives in App so it survives
// in-tab navigation. This just renders the bar and reports start/stop intent.
export function RecorderPanel({ isRecording, elapsedMs, busy, error, onStart, onStop }: Props) {
  return (
    <div className="recorder">
      {isRecording && <span className="rec-dot" aria-hidden="true" />}
      <span className="timer num">{msToMmss(elapsedMs)}</span>
      {!isRecording ? (
        <button className="btn btn-primary" onClick={onStart} disabled={busy}>녹음 시작</button>
      ) : (
        <button className="btn btn-secondary" onClick={onStop} disabled={busy}>녹음 정지</button>
      )}
      {error && <p role="alert" className="warn-text">{error}</p>}
    </div>
  );
}
