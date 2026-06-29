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

const LANGUAGE_LABELS: Record<string, string> = {
  ko: "한국어",
  en: "English",
  auto: "자동 감지",
};

export function languageLabel(language: string | null): string | null {
  if (!language) return null;
  return LANGUAGE_LABELS[language] ?? language;
}

const STAGE_LABELS: Record<string, string> = {
  loading: "모델 로딩",
  transcribing: "음성 인식",
  aligning: "정렬",
  diarizing: "화자 분리",
};

export function stageLabel(stage: string | null): string | null {
  if (!stage) return null;
  // Chunked transcription reports progress as "transcribing:k/n".
  const m = /^transcribing:(\d+)\/(\d+)$/.exec(stage);
  if (m) return `${STAGE_LABELS.transcribing} (${m[1]}/${m[2]})`;
  return STAGE_LABELS[stage] ?? stage;
}
