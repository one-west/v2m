import { useEffect, useRef, useState } from "react";
import { exportUrl, getRecording, patchRecording, retryRecording } from "../../lib/api";
import type { MeetingMeta, RecordingDetail as Detail, TranscriptSegment } from "../../lib/types";
import { msToMmss, statusLabel } from "../../lib/format";
import { StatusBadge } from "./StatusBadge";
import { CopyForClaude } from "./CopyForClaude";
import { MeetingForm } from "../meeting/MeetingForm";

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
  const [title, setTitle] = useState("");
  const [meta, setMeta] = useState<MeetingMeta>({});
  const [saving, setSaving] = useState(false);
  const [saveState, setSaveState] = useState<"idle" | "saved" | "error">("idle");
  const [reloadToken, setReloadToken] = useState(0);
  const activeRef = useRef(true);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    activeRef.current = true;
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    let seeded = false;

    async function load() {
      let loaded: Detail;
      try {
        loaded = await getRecording(id);
      } catch {
        return;
      }
      if (!activeRef.current) return;
      setDetail(loaded);
      if (!seeded) {
        setTitle(loaded.title);
        setMeta(loaded.meta ?? {});
        seeded = true;
      }
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

  if (!detail) return <p className="empty">불러오는 중…</p>;

  async function handleSave() {
    setSaving(true);
    setSaveState("idle");
    try {
      await patchRecording(id, { title, meta });
      setSaveState("saved");
    } catch {
      setSaveState("error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="detail">
      <button className="btn btn-secondary" onClick={onBack}>← 목록</button>

      <div className="card">
        <h2>회의 정보 <StatusBadge status={detail.status} /></h2>
        <MeetingForm title={title} meta={meta}
          onChange={(next) => { setTitle(next.title); setMeta(next.meta); }} />
        <div className="btn-group">
          <button className="btn btn-secondary" onClick={handleSave} disabled={saving}>저장</button>
          {saveState === "saved" && <span role="status" className="sub">저장되었습니다</span>}
          {saveState === "error" && <span role="alert" className="warn-text">저장에 실패했습니다</span>}
        </div>
      </div>

      {detail.status === "failed" && (
        <div className="card" role="alert">
          <p className="warn-text">전사 실패: {detail.error}</p>
          <button className="btn btn-secondary"
            onClick={async () => { await retryRecording(id); setReloadToken((t) => t + 1); }}>
            다시 시도
          </button>
        </div>
      )}

      {detail.status === "done" && detail.transcript && detail.transcript.segments.length > 0 && (
        <>
          <div className="card">
            <h2>회의록 만들기</h2>
            <p className="sub">전사본과 프롬프트를 복사해 claude.ai 데스크탑 앱에 붙여넣으세요.</p>
            <CopyForClaude id={id} />
            <div className="btn-group">
              <a className="btn btn-secondary" href={exportUrl(id, "md")}>Markdown 내보내기</a>
              <a className="btn btn-secondary" href={exportUrl(id, "txt")}>TXT 내보내기</a>
            </div>
          </div>

          <div className="card">
            <h2>전사본</h2>
            <div className="transcript">
              {groupSegments(detail.transcript.segments).map((g, i) => (
                <div className="seg" key={i}>
                  <div className="head">
                    <span className="speaker-chip">{g.speaker}</span>
                    <span className="ts num">[{msToMmss(g.startMs)}]</span>
                  </div>
                  {g.lines.map((line, j) => <p key={j}>{line}</p>)}
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {detail.status === "done" && detail.transcript && detail.transcript.segments.length === 0 && (
        <div className="card" role="alert">
          <p className="warn-text">음성이 감지되지 않았습니다. 녹음이 무음이거나 소리가 너무 작을 수 있어요 — 다시 녹음해 주세요.</p>
        </div>
      )}

      {(detail.status === "recorded" || detail.status === "transcribing") && (
        <p className="empty">{statusLabel(detail.status)}… 잠시만 기다려 주세요.</p>
      )}
    </div>
  );
}
