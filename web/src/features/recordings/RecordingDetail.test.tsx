import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RecordingDetail, groupSegments } from "./RecordingDetail";

vi.mock("../../lib/api", () => ({
  getRecording: vi.fn(),
  patchRecording: vi.fn().mockResolvedValue({}),
  retryRecording: vi.fn().mockResolvedValue(undefined),
  exportUrl: (id: string, f: string) => `/api/recordings/${id}/export?format=${f}`,
}));
vi.mock("./CopyForClaude", () => ({ CopyForClaude: () => <div>copy-stub</div> }));
import { getRecording, patchRecording, retryRecording } from "../../lib/api";

const doneDetail = {
  id: "a", title: "주간회의", status: "done", created_at: "x", duration_sec: 60, error: null,
  meta: { location: "A" }, language: "ko",
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
  it("renders transcript + export link when done and saves title+meta", async () => {
    (getRecording as ReturnType<typeof vi.fn>).mockResolvedValue(doneDetail);
    render(<RecordingDetail id="a" onBack={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("안녕하세요")).toBeInTheDocument());
    expect(screen.getByText("SPEAKER_00")).toBeInTheDocument();
    expect(screen.getByText("[00:00]")).toBeInTheDocument();
    expect(screen.getByText("전사 언어: 한국어")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Markdown/ }))
      .toHaveAttribute("href", "/api/recordings/a/export?format=md");

    await userEvent.click(screen.getByRole("button", { name: "저장" }));
    expect(patchRecording).toHaveBeenCalledWith("a", { title: "주간회의", meta: { location: "A" } });
    await waitFor(() => expect(screen.getByText("저장되었습니다")).toBeInTheDocument());
  });

  it("shows the current transcription stage while transcribing", async () => {
    (getRecording as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: "a", title: "주간회의", status: "transcribing", created_at: "x", duration_sec: 60,
      error: null, meta: null, language: "ko", stage: "diarizing", transcript: null,
    });
    render(<RecordingDetail id="a" onBack={vi.fn()} />);
    await waitFor(() => expect(screen.getByText(/화자 분리/)).toBeInTheDocument());
  });

  it("shows a no-speech notice (not transcript/copy) when done with 0 segments", async () => {
    (getRecording as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...doneDetail,
      transcript: { segments: [], full_text: "", language: "ko" },
    });
    render(<RecordingDetail id="a" onBack={vi.fn()} />);
    await waitFor(() => expect(screen.getByText(/음성이 감지되지 않았습니다/)).toBeInTheDocument());
    expect(screen.queryByText("전사본")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Markdown/ })).not.toBeInTheDocument();
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

  it("polls while transcribing then shows transcript when done", async () => {
    vi.useFakeTimers();
    const transcribingDetail = {
      id: "a", title: "주간회의", status: "transcribing", created_at: "x",
      duration_sec: 60, error: null, transcript: null, meta: null,
    };
    (getRecording as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(transcribingDetail)
      .mockResolvedValueOnce(doneDetail);

    render(<RecordingDetail id="a" onBack={vi.fn()} />);
    await act(async () => {});
    expect(screen.getByText(/잠시만 기다려 주세요/)).toBeInTheDocument();

    await act(async () => { vi.advanceTimersByTime(3000); });
    await act(async () => {});
    expect(screen.getByText("안녕하세요")).toBeInTheDocument();

    vi.useRealTimers();
  });
});
