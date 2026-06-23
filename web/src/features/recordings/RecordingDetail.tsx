import { useEffect, useState } from "react";
import { exportUrl, getRecording, retryRecording } from "../../lib/api";
import type { RecordingDetail as Detail, TranscriptSegment } from "../../lib/types";
import { msToMmss, statusLabel } from "../../lib/format";
import { StatusBadge } from "./StatusBadge";
import { CopyForClaude } from "./CopyForClaude";

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

  async function load() {
    setDetail(await getRecording(id));
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

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
              load();
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
