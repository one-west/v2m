import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useRecorder } from "./useRecorder";

class FakeMediaRecorder {
  static isTypeSupported() {
    return true;
  }
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  mimeType = "audio/webm;codecs=opus";
  state = "inactive";
  constructor(public stream: { getTracks: () => { stop: () => void }[] }) {}
  start() {
    this.state = "recording";
    this.ondataavailable?.({ data: new Blob(["chunk"], { type: this.mimeType }) });
  }
  stop() {
    this.state = "inactive";
    this.onstop?.();
  }
}

beforeEach(() => {
  vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
  vi.stubGlobal("navigator", {
    mediaDevices: {
      getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] }),
    },
  });
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useRecorder", () => {
  it("records then returns a blob on stop", async () => {
    const { result } = renderHook(() => useRecorder());
    await act(async () => {
      await result.current.start();
    });
    expect(result.current.isRecording).toBe(true);

    let blob: Blob = new Blob();
    await act(async () => {
      blob = await result.current.stop();
    });
    expect(result.current.isRecording).toBe(false);
    expect(blob.size).toBeGreaterThan(0);
  });
});
