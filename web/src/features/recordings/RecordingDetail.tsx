import { useEffect, useRef, useState } from "react";
import { exportUrl, getRecording, retryRecording } from "../../lib/api";
import type { RecordingDetail as Detail, TranscriptSegment } from "../../lib/types";
import { msToMmss, statusLabel } from "../../lib/format";
import { StatusBadge } from "./StatusBadge";
import { CopyForClaude } from "./CopyForClaude";

const POLL_MS = 3000;

interface Group {
  speaker: string;
  startMs: number;
  lines: string[];
}

export function groupSegments(segments: TranscriptSegment[]): Group[] {
  const groups: Group[] = [];
  for (const seg of segments) {
    const last = groups[groups.length - 1];
    if (last && last.speaker === seg.speaker) {
      last.lines.push(seg.text);
    } else {
      groups.push({ speaker: seg.speaker, startMs: seg.start_ms, lines: [seg.text] });
    }
  }
  return groups;
}

export function RecordingDetail({ id, onBack }: { id: string; onBack: () => void }) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const activeRef = useRef(true);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    activeRef.current = true;
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);

    async function load() {
      let loaded: Detail;
      try {
        loaded = await getRecording(id);
      } catch {
        return;
      }
      if (!activeRef.current) return;
      setDetail(loaded);
      if (loaded.status === "recorded" || loaded.status === "transcribing") {
        timerRef.current = window.setTimeout(load, POLL_MS);
      }
    }

    load();

    return () => {
      activeRef.current = false;
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, reloadToken]);

  if (!detail) return <p>불러오는 중…</p>;

  return (
    <div className="detail">
      <button onClick={onBack}>← 목록</button>
      <h2>{detail.title}</h2>
      <StatusBadge status={detail.status} />

      {detail.status === "failed" && (
        <div role="alert">
          <p>전사 실패: {detail.error}</p>
          <button
            onClick={async () => {
              await retryRecording(id);
              setReloadToken((t) => t + 1);
            }}
          >
            다시 시도
          </button>
        </div>
      )}

      {detail.status === "done" && detail.transcript && (
        <>
          <CopyForClaude id={id} />
          <div className="export">
            <a href={exportUrl(id, "md")}>Markdown 내보내기</a>
            <a href={exportUrl(id, "txt")}>TXT 내보내기</a>
          </div>
          <div className="transcript">
            {groupSegments(detail.transcript.segments).map((g, i) => (
              <div className="seg" key={i}>
                <div className="head">
                  [{msToMmss(g.startMs)}] {g.speaker}
                </div>
                {g.lines.map((line, j) => (
                  <p key={j}>{line}</p>
                ))}
              </div>
            ))}
          </div>
        </>
      )}

      {(detail.status === "recorded" || detail.status === "transcribing") && (
        <p>{statusLabel(detail.status)}… 잠시만 기다려 주세요.</p>
      )}
    </div>
  );
}
