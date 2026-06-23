import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RecordingDetail, groupSegments } from "./RecordingDetail";

vi.mock("../../lib/api", () => ({
  getRecording: vi.fn(),
  retryRecording: vi.fn().mockResolvedValue(undefined),
  exportUrl: (id: string, f: string) => `/api/recordings/${id}/export?format=${f}`,
}));
vi.mock("./CopyForClaude", () => ({ CopyForClaude: () => <div>copy-stub</div> }));
import { getRecording, retryRecording } from "../../lib/api";

const doneDetail = {
  id: "a", title: "주간회의", status: "done", created_at: "x", duration_sec: 60, error: null,
  transcript: {
    segments: [
      { speaker: "SPEAKER_00", start_ms: 0, end_ms: 2000, text: "안녕하세요" },
      { speaker: "SPEAKER_00", start_ms: 2000, end_ms: 4000, text: "시작합니다" },
      { speaker: "SPEAKER_01", start_ms: 65000, end_ms: 67000, text: "네" },
    ],
    full_text: "안녕하세요 시작합니다 네", language: "ko",
  },
};

beforeEach(() => vi.clearAllMocks());

describe("groupSegments", () => {
  it("merges consecutive same-speaker segments", () => {
    const groups = groupSegments(doneDetail.transcript.segments);
    expect(groups).toHaveLength(2);
    expect(groups[0].lines).toEqual(["안녕하세요", "시작합니다"]);
    expect(groups[1].speaker).toBe("SPEAKER_01");
  });
});

describe("RecordingDetail", () => {
  it("renders grouped transcript when done", async () => {
    (getRecording as ReturnType<typeof vi.fn>).mockResolvedValue(doneDetail);
    render(<RecordingDetail id="a" onBack={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("안녕하세요")).toBeInTheDocument());
    expect(screen.getByText(/\[00:00\] SPEAKER_00/)).toBeInTheDocument();
    expect(screen.getByText(/\[01:05\] SPEAKER_01/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Markdown/ })).toHaveAttribute(
      "href", "/api/recordings/a/export?format=md",
    );
  });

  it("shows retry on failed and reloads", async () => {
    (getRecording as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ ...doneDetail, status: "failed", transcript: null, error: "boom" })
      .mockResolvedValueOnce(doneDetail);
    render(<RecordingDetail id="a" onBack={vi.fn()} />);
    await waitFor(() => expect(screen.getByText(/boom/)).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    expect(retryRecording).toHaveBeenCalledWith("a");
    await waitFor(() => expect(screen.getByText("안녕하세요")).toBeInTheDocument());
  });
});
