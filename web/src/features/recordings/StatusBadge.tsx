import type { RecordingStatus } from "../../lib/types";
import { statusLabel } from "../../lib/format";

export function StatusBadge({ status }: { status: RecordingStatus }) {
  return <span className={`badge badge-${status}`}>{statusLabel(status)}</span>;
}
