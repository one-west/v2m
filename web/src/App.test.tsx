import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";

vi.mock("./lib/api", () => ({
  listRecordings: vi.fn().mockResolvedValue([
    { id: "a", title: "주간회의", status: "done", created_at: "x", duration_sec: 1, meta: null },
  ]),
  deleteRecording: vi.fn().mockResolvedValue(undefined),
  uploadRecording: vi.fn().mockResolvedValue({ id: "a" }),
  patchRecording: vi.fn().mockResolvedValue({}),
  getRecording: vi.fn().mockResolvedValue({
    id: "a", title: "주간회의", status: "done", created_at: "x", duration_sec: 1, error: null, meta: null,
    transcript: { segments: [{ speaker: "SPEAKER_00", start_ms: 0, end_ms: 1000, text: "안녕" }], full_text: "안녕", language: "ko" },
  }),
  exportUrl: vi.fn().mockReturnValue("#"),
  retryRecording: vi.fn().mockResolvedValue(undefined),
}));
vi.mock("./hooks/useRecorder", () => ({
  useRecorder: () => ({ isRecording: false, elapsedMs: 0, start: vi.fn(), stop: vi.fn() }),
}));
vi.mock("./features/recordings/CopyForClaude", () => ({ CopyForClaude: () => <div>copy</div> }));

beforeEach(() => vi.clearAllMocks());

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
});
