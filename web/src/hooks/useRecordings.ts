import { useCallback, useEffect, useRef, useState } from "react";
import { listRecordings } from "../lib/api";
import type { RecordingSummary } from "../lib/types";

const ACTIVE_POLL_MS = 3000;
const IDLE_POLL_MS = 12000;

export function useRecordings() {
  const [recordings, setRecordings] = useState<RecordingSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const timerRef = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    const rows = await listRecordings();
    setRecordings(rows);
    setLoading(false);
    return rows;
  }, []);

  useEffect(() => {
    let active = true;
    async function tick() {
      const rows = await refresh().catch(() => [] as RecordingSummary[]);
      if (!active) return;
      const busy = rows.some((r) => r.status === "recorded" || r.status === "transcribing");
      timerRef.current = window.setTimeout(tick, busy ? ACTIVE_POLL_MS : IDLE_POLL_MS);
    }
    tick();
    return () => {
      active = false;
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
  }, [refresh]);

  return { recordings, loading, refresh };
}
