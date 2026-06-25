import { useEffect } from "react";

/**
 * While `active`, warn the user before the page unloads (refresh / close tab /
 * navigate to another URL) so an in-progress, not-yet-uploaded recording isn't
 * silently lost. The browser shows its native confirm dialog.
 */
export function useBeforeUnloadGuard(active: boolean): void {
  useEffect(() => {
    if (!active) return;
    function handler(e: BeforeUnloadEvent) {
      e.preventDefault();
      e.returnValue = ""; // required for Chrome/Edge to show the prompt
    }
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [active]);
}
