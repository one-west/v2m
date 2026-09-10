import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";

vi.mock("./lib/api", () => ({
  listRecordings: vi.fn().mockResolvedValue([
    { id: "a", title: "주간회의", status: "done", created_at: "x", meta: null },
  ]),
  deleteRecording: vi.fn().mockResolvedValue(undefined),
  uploadRecording: vi.fn().mockResolvedValue({ id: "a" }),
  patchRecording: vi.fn().mockResolvedValue({}),
  getRecording: vi.fn().mockResolvedValue({
    id: "a", title: "주간회의", status: "done", created_at: "x", error: null, meta: null,
    transcript: { segments: [{ speaker: "SPEAKER_00", start_ms: 0, end_ms: 1000, text: "안녕" }], full_text: "안녕", language: "ko" },
  }),
  exportUrl: vi.fn().mockReturnValue("#"),
  audioUrl: vi.fn().mockReturnValue("#"),
  retryRecording: vi.fn().mockResolvedValue(undefined),
}));
const recorderState = { isRecording: false, elapsedMs: 0, start: vi.fn(), stop: vi.fn() };
// Captures the options App passes in, so a test can fire onChunk like MediaRecorder does.
type RecorderOpts = { onChunk?: (b: Blob) => void };
const useRecorderMock = vi.fn((_opts?: RecorderOpts) => recorderState);
vi.mock("./hooks/useRecorder", () => ({ useRecorder: (opts?: RecorderOpts) => useRecorderMock(opts) }));
vi.mock("./features/recordings/CopyForClaude", () => ({ CopyForClaude: () => <div>copy</div> }));
vi.mock("./lib/recordingStore", () => ({
  getPendingSession: vi.fn().mockResolvedValue(null),
  clearSession: vi.fn().mockResolvedValue(undefined),
  beginSession: vi.fn().mockResolvedValue(undefined),
  appendChunk: vi.fn().mockResolvedValue(undefined),
}));
import { deleteRecording, uploadRecording } from "./lib/api";
import { appendChunk, getPendingSession } from "./lib/recordingStore";

beforeEach(() => {
  vi.clearAllMocks();
  recorderState.isRecording = false;
  // clearAllMocks keeps implementations, so restore the happy path for every mock a
  // failure-case test overrides — otherwise the rejection leaks into later tests.
  (getPendingSession as ReturnType<typeof vi.fn>).mockResolvedValue(null);
  (uploadRecording as ReturnType<typeof vi.fn>).mockResolvedValue({ id: "a" });
  (deleteRecording as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
  (appendChunk as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
});

describe("App", () => {
  it("shows home (new-meeting + list), then opens detail on select", async () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /V2M/ })).toBeInTheDocument();
    expect(screen.getByText("새 회의")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "녹음 시작" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "주간회의" })).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "주간회의" }));
    await waitFor(() => expect(screen.getByText("안녕")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "← 목록" })).toBeInTheDocument();
  });

  it("keeps recording while navigating to a detail view (no stop, shows top-bar 정지)", async () => {
    recorderState.isRecording = true;
    render(<App />);
    await waitFor(() => expect(screen.getByRole("button", { name: "주간회의" })).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "주간회의" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "← 목록" })).toBeInTheDocument());

    // Recording continues across the in-tab navigation: never stopped, and the
    // persistent top-bar 정지 control is shown on the detail view.
    expect(recorderState.stop).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "정지" })).toBeInTheDocument();
  });

  it("offers to recover a buffered recording and uploads it", async () => {
    (getPendingSession as ReturnType<typeof vi.fn>).mockResolvedValue({
      meta: { title: "끊긴회의", meta: { location: "A" }, language: "ko" },
      audio: new Blob(["x"]),
    });
    render(<App />);
    await waitFor(() => expect(screen.getByText("중단된 녹음 발견")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "복구" }));
    await waitFor(() => expect(uploadRecording).toHaveBeenCalled());
    const [, opts] = (uploadRecording as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(opts).toEqual({ title: "끊긴회의", meta: { location: "A" }, language: "ko" });
    await waitFor(() => expect(screen.queryByText("중단된 녹음 발견")).not.toBeInTheDocument());
  });

  it("keeps the recovery offer and explains the failure when recovery upload fails", async () => {
    (getPendingSession as ReturnType<typeof vi.fn>).mockResolvedValue({
      meta: { title: "끊긴회의", meta: {}, language: "ko" },
      audio: new Blob(["x"]),
    });
    (uploadRecording as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("HTTP 500"));
    render(<App />);
    await waitFor(() => expect(screen.getByText("중단된 녹음 발견")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "복구" }));

    // The buffered audio is the only copy — the offer must survive a failed upload
    // so the user can retry instead of silently losing the recording.
    await waitFor(() => expect(screen.getByText(/복구에 실패/)).toBeInTheDocument());
    expect(screen.getByText("중단된 녹음 발견")).toBeInTheDocument();
  });

  it("reports a failed delete instead of leaving the row silently in place", async () => {
    (deleteRecording as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("HTTP 500"));
    render(<App />);
    await waitFor(() => expect(screen.getByRole("button", { name: "주간회의" })).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "주간회의 삭제" }));
    await waitFor(() => expect(screen.getByText(/삭제에 실패/)).toBeInTheDocument());
  });

  it("warns when the durable recording buffer stops accepting chunks", async () => {
    (appendChunk as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("QuotaExceededError"));
    recorderState.isRecording = true;
    render(<App />);

    // App wires its own onChunk into useRecorder; invoke it the way MediaRecorder would.
    const calls = useRecorderMock.mock.calls;
    calls[calls.length - 1][0]?.onChunk?.(new Blob(["chunk"]));

    await waitFor(() => expect(screen.getByText(/복구 백업이 중단/)).toBeInTheDocument());
  });
});
