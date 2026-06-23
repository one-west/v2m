export type RecordingStatus = "recorded" | "transcribing" | "done" | "failed";

export interface MeetingMeta {
  date?: string;
  time?: string;
  location?: string;
  attendees?: string;
  agenda?: string;
}

export interface RecordingSummary {
  id: string;
  title: string;
  status: RecordingStatus;
  created_at: string;
  duration_sec: number | null;
  meta: MeetingMeta | null;
}

export interface TranscriptSegment {
  speaker: string;
  start_ms: number;
  end_ms: number;
  text: string;
}

export interface Transcript {
  segments: TranscriptSegment[];
  full_text: string;
  language: string;
}

export interface RecordingDetail {
  id: string;
  title: string;
  status: RecordingStatus;
  created_at: string;
  duration_sec: number | null;
  error: string | null;
  transcript: Transcript | null;
  meta: MeetingMeta | null;
}

export interface PromptBundle {
  prompt: string;
  transcript_text: string;
  char_count: number;
  too_long: boolean;
}
