import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import * as api from "./api";

function mockFetch(body: unknown, ok = true, status = 200) {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    json: () => Promise.resolve(body),
  });
}

beforeEach(() => {
  vi.stubGlobal("fetch", mockFetch([]));
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api", () => {
  it("listRecordings GETs /api/recordings", async () => {
    const f = mockFetch([{ id: "1" }]);
    vi.stubGlobal("fetch", f);
    const rows = await api.listRecordings();
    expect(f).toHaveBeenCalledWith("/api/recordings");
    expect(rows).toEqual([{ id: "1" }]);
  });

  it("uploadRecording POSTs multipart with file and title", async () => {
    const f = mockFetch({ id: "1", title: "T", status: "recorded", created_at: "x" }, true, 201);
    vi.stubGlobal("fetch", f);
    await api.uploadRecording(new Blob(["a"]), "T");
    const [url, opts] = f.mock.calls[0];
    expect(url).toBe("/api/recordings");
    expect(opts.method).toBe("POST");
    expect(opts.body).toBeInstanceOf(FormData);
    expect((opts.body as FormData).get("title")).toBe("T");
    expect((opts.body as FormData).get("file")).toBeInstanceOf(File);
  });

  it("retryRecording POSTs retry", async () => {
    const f = mockFetch({}, true, 200);
    vi.stubGlobal("fetch", f);
    await api.retryRecording("1");
    expect(f).toHaveBeenCalledWith("/api/recordings/1/retry", { method: "POST" });
  });

  it("deleteRecording tolerates 204", async () => {
    const f = mockFetch(null, false, 204);
    vi.stubGlobal("fetch", f);
    await expect(api.deleteRecording("1")).resolves.toBeUndefined();
  });

  it("throws on non-ok json response", async () => {
    vi.stubGlobal("fetch", mockFetch({}, false, 500));
    await expect(api.listRecordings()).rejects.toThrow(/500/);
  });

  it("exportUrl builds a query string", () => {
    expect(api.exportUrl("abc", "md")).toBe("/api/recordings/abc/export?format=md");
  });
});
