import type { PromptBundle, RecordingDetail, RecordingSummary } from "./types";

async function jsonOrThrow<T>(resp: Response): Promise<T> {
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return (await resp.json()) as T;
}

export async function listRecordings(): Promise<RecordingSummary[]> {
  return jsonOrThrow(await fetch("/api/recordings"));
}

export async function getRecording(id: string): Promise<RecordingDetail> {
  return jsonOrThrow(await fetch(`/api/recordings/${id}`));
}

export async function uploadRecording(blob: Blob, title?: string): Promise<RecordingSummary> {
  const form = new FormData();
  form.append("file", new File([blob], "recording.webm", { type: blob.type || "audio/webm" }));
  if (title) form.append("title", title);
  return jsonOrThrow(await fetch("/api/recordings", { method: "POST", body: form }));
}

export async function retryRecording(id: string): Promise<void> {
  const resp = await fetch(`/api/recordings/${id}/retry`, { method: "POST" });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
}

export async function deleteRecording(id: string): Promise<void> {
  const resp = await fetch(`/api/recordings/${id}`, { method: "DELETE" });
  if (!resp.ok && resp.status !== 204) throw new Error(`HTTP ${resp.status}`);
}

export async function getPrompt(id: string): Promise<PromptBundle> {
  return jsonOrThrow(await fetch(`/api/recordings/${id}/prompt`));
}

export function exportUrl(id: string, format: "md" | "txt"): string {
  return `/api/recordings/${id}/export?format=${format}`;
}
