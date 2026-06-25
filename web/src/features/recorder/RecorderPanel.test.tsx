import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RecorderPanel } from "./RecorderPanel";

const base = {
  isRecording: false,
  elapsedMs: 0,
  busy: false,
  error: null as string | null,
  onStart: vi.fn(),
  onStop: vi.fn(),
};

describe("RecorderPanel (presentational)", () => {
  it("fires onStart when idle", async () => {
    const onStart = vi.fn();
    render(<RecorderPanel {...base} onStart={onStart} />);
    await userEvent.click(screen.getByRole("button", { name: "녹음 시작" }));
    expect(onStart).toHaveBeenCalled();
  });

  it("shows the timer + stop button and fires onStop while recording", async () => {
    const onStop = vi.fn();
    render(<RecorderPanel {...base} isRecording elapsedMs={65000} onStop={onStop} />);
    expect(screen.getByText("01:05")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "녹음 정지" }));
    expect(onStop).toHaveBeenCalled();
  });

  it("renders an error", () => {
    render(<RecorderPanel {...base} error="업로드에 실패했습니다." />);
    expect(screen.getByRole("alert")).toHaveTextContent("업로드에 실패했습니다.");
  });
});
