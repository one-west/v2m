import { describe, it, expect } from "vitest";
import { renderHook } from "@testing-library/react";
import { useBeforeUnloadGuard } from "./useBeforeUnloadGuard";

function fireBeforeUnload(): boolean {
  const e = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(e);
  return e.defaultPrevented;
}

describe("useBeforeUnloadGuard", () => {
  it("blocks unload while active", () => {
    renderHook(() => useBeforeUnloadGuard(true));
    expect(fireBeforeUnload()).toBe(true);
  });

  it("does not block when inactive", () => {
    renderHook(() => useBeforeUnloadGuard(false));
    expect(fireBeforeUnload()).toBe(false);
  });

  it("removes the listener on unmount", () => {
    const { unmount } = renderHook(() => useBeforeUnloadGuard(true));
    unmount();
    expect(fireBeforeUnload()).toBe(false);
  });
});
