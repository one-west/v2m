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
