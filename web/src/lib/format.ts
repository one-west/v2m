import type { MeetingMeta, RecordingStatus } from "./types";

export function msToMmss(ms: number): string {
  const total = Math.floor(ms / 1000);
  const m = String(Math.floor(total / 60)).padStart(2, "0");
  const s = String(total % 60).padStart(2, "0");
  return `${m}:${s}`;
}

const STATUS_LABELS: Record<RecordingStatus, string> = {
  recorded: "대기",
  transcribing: "전사중",
  done: "완료",
  failed: "실패",
};

export function statusLabel(status: RecordingStatus): string {
  return STATUS_LABELS[status];
}

export function attendeesCount(meta: MeetingMeta | null): number {
  if (!meta?.attendees) return 0;
  return meta.attendees.split(",").map((s) => s.trim()).filter(Boolean).length;
}
