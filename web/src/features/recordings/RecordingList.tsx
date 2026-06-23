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
