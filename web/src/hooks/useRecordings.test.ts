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
});
