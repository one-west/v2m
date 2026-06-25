import "fake-indexeddb/auto";
import { describe, it, expect, beforeEach } from "vitest";
import { beginSession, appendChunk, clearSession, getPendingSession } from "./recordingStore";

const SAMPLE = { title: "T", meta: { location: "A" }, language: "ko" };

beforeEach(async () => {
  await clearSession();
});

describe("recordingStore", () => {
  it("returns null when there is no active session", async () => {
    expect(await getPendingSession()).toBeNull();
  });

  it("returns null for a session with meta but no chunks", async () => {
    await beginSession(SAMPLE);
    expect(await getPendingSession()).toBeNull();
  });

  it("persists chunks in order and recovers the session", async () => {
    await beginSession(SAMPLE);
    await appendChunk(new Blob(["aa"], { type: "audio/webm" }));
    await appendChunk(new Blob(["bbb"], { type: "audio/webm" }));

    const pending = await getPendingSession();
    expect(pending?.meta).toEqual(SAMPLE);
    expect(pending?.audio.size).toBe(5); // 2 + 3 bytes, assembled in order
  });

  it("beginSession discards a previous session's chunks", async () => {
    await beginSession(SAMPLE);
    await appendChunk(new Blob(["a"]));
    await beginSession({ ...SAMPLE, title: "new" });
    expect(await getPendingSession()).toBeNull(); // fresh session has no chunks yet
  });

  it("clearSession removes meta and chunks", async () => {
    await beginSession(SAMPLE);
    await appendChunk(new Blob(["a"]));
    await clearSession();
    expect(await getPendingSession()).toBeNull();
  });
});
