import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";

vi.mock("../lib/api", () => ({ listRecordings: vi.fn() }));
import { listRecordings } from "../lib/api";
import { useRecordings } from "./useRecordings";

const sample = [{ id: "a", title: "T", status: "done", created_at: "x", duration_sec: null }];

beforeEach(() => {
  vi.clearAllMocks();
  (listRecordings as ReturnType<typeof vi.fn>).mockResolvedValue(sample);
});

describe("useRecordings", () => {
  it("loads recordings on mount", async () => {
    const { result } = renderHook(() => useRecordings());
    await waitFor(() => expect(result.current.recordings).toEqual(sample));
    expect(result.current.loading).toBe(false);
  });

  it("refresh re-fetches", async () => {
    const { result } = renderHook(() => useRecordings());
    await waitFor(() => expect(result.current.recordings).toEqual(sample));
    await act(async () => {
      await result.current.refresh();
    });
    expect(listRecordings).toHaveBeenCalledTimes(2);
  });

  it("surfaces an error flag when the load fails", async () => {
    (listRecordings as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("boom"));
    const { result } = renderHook(() => useRecordings());
    await waitFor(() => expect(result.current.error).toBe(true));
    expect(result.current.loading).toBe(false);
  });

  it("clears the error flag once a later load succeeds", async () => {
    (listRecordings as ReturnType<typeof vi.fn>)
      .mockRejectedValueOnce(new Error("boom"))
      .mockResolvedValue(sample);
    const { result } = renderHook(() => useRecordings());
    await waitFor(() => expect(result.current.error).toBe(true));
    await act(async () => {
      await result.current.refresh();
    });
    expect(result.current.error).toBe(false);
  });

  it("does not call setState after unmount (no act() warning)", async () => {
    // Use fake timers so the polling setTimeout never fires after unmount.
    vi.useFakeTimers();
    // Capture any console.error calls (act() warnings are emitted there).
    const errorSpy = vi.spyOn(console, "error");

    let resolveFirst!: (v: typeof sample) => void;
    const pendingFetch = new Promise<typeof sample>((res) => {
      resolveFirst = res;
    });
    (listRecordings as ReturnType<typeof vi.fn>).mockReturnValueOnce(pendingFetch);

    const { unmount } = renderHook(() => useRecordings());

    // Unmount before the in-flight fetch resolves.
    unmount();

    // Now resolve the fetch — setState must NOT be called.
    await act(async () => {
      resolveFirst(sample);
      // Flush microtasks so the promise chain runs.
      await Promise.resolve();
    });

    expect(errorSpy).not.toHaveBeenCalled();
    errorSpy.mockRestore();
    vi.useRealTimers();
  });
});
