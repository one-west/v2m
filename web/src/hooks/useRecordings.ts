import { useCallback, useEffect, useRef, useState } from "react";
import { listRecordings } from "../lib/api";
import type { RecordingSummary } from "../lib/types";

const ACTIVE_POLL_MS = 3000;
const IDLE_POLL_MS = 12000;

export function useRecordings() {
  const [recordings, setRecordings] = useState<RecordingSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const timerRef = useRef<number | null>(null);
  // Guard: set to false on unmount so in-flight fetches don't call setState.
  const activeRef = useRef(true);

  const refresh = useCallback(async () => {
    const rows = await listRecordings();
    if (activeRef.current) {
      setRecordings(rows);
      setLoading(false);
    }
    return rows;
  }, []);

  useEffect(() => {
    activeRef.current = true;
    let active = true;
    async function tick() {
      let rows: RecordingSummary[];
      try {
        rows = await refresh();
      } catch {
        rows = [] as RecordingSummary[];
        // Ensure loading spinner clears even on first-fetch error.
        if (activeRef.current) setLoading(false);
      }
      if (!active) return;
      const busy = rows.some((r) => r.status === "recorded" || r.status === "transcribing");
      timerRef.current = window.setTimeout(tick, busy ? ACTIVE_POLL_MS : IDLE_POLL_MS);
    }
    tick();
    return () => {
      active = false;
      activeRef.current = false;
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    };
  }, [refresh]);

  return { recordings, loading, refresh };
}
