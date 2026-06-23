import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RecorderPanel } from "./RecorderPanel";

const startMock = vi.fn().mockResolvedValue(undefined);
const stopMock = vi.fn().mockResolvedValue(new Blob(["x"]));
const recorderState = { isRecording: false, elapsedMs: 0, start: startMock, stop: stopMock };

vi.mock("../../hooks/useRecorder", () => ({ useRecorder: () => recorderState }));
vi.mock("../../lib/api", () => ({ uploadRecording: vi.fn().mockResolvedValue({ id: "1" }) }));
import { uploadRecording } from "../../lib/api";

beforeEach(() => {
  vi.clearAllMocks();
  recorderState.isRecording = false;
});

describe("RecorderPanel", () => {
  it("starts recording on click", async () => {
    render(<RecorderPanel title="회의" meta={{}} onUploaded={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "녹음 시작" }));
    expect(startMock).toHaveBeenCalled();
  });

  it("uploads with title+meta and notifies on stop", async () => {
    recorderState.isRecording = true;
    const onUploaded = vi.fn();
    render(<RecorderPanel title="회의" meta={{ location: "A" }} onUploaded={onUploaded} />);
    await userEvent.click(screen.getByRole("button", { name: "녹음 정지" }));
    await waitFor(() => expect(uploadRecording).toHaveBeenCalled());
    const [, opts] = (uploadRecording as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(opts).toEqual({ title: "회의", meta: { location: "A" } });
    expect(onUploaded).toHaveBeenCalled();
  });
});
