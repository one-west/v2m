import type { MeetingMeta } from "../../lib/types";

interface Props {
  title: string;
  meta: MeetingMeta;
  onChange: (next: { title: string; meta: MeetingMeta }) => void;
}

export function MeetingForm({ title, meta, onChange }: Props) {
  function setMeta(key: keyof MeetingMeta, value: string) {
    const next = { ...meta };
    if (value) next[key] = value;
    else delete next[key];
    onChange({ title, meta: next });
  }

  return (
    <div className="meeting-form">
      <div className="grid-2">
        <div className="field">
          <label htmlFor="mf-title">제목</label>
          <input id="mf-title" value={title}
            onChange={(e) => onChange({ title: e.target.value, meta })} />
        </div>
        <div className="field">
          <label htmlFor="mf-date">일자</label>
          <input id="mf-date" type="date" value={meta.date ?? ""}
            onChange={(e) => setMeta("date", e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="mf-time">시간</label>
          <input id="mf-time" type="time" value={meta.time ?? ""}
            onChange={(e) => setMeta("time", e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="mf-loc">장소</label>
          <input id="mf-loc" value={meta.location ?? ""}
            onChange={(e) => setMeta("location", e.target.value)} />
        </div>
      </div>
      <div className="field" style={{ marginTop: 14 }}>
        <label htmlFor="mf-att">참석자</label>
        <textarea id="mf-att" value={meta.attendees ?? ""}
          placeholder="쉼표로 구분 (예: 홍길동, 김철수)"
          onChange={(e) => setMeta("attendees", e.target.value)} />
      </div>
      <div className="field" style={{ marginTop: 14 }}>
        <label htmlFor="mf-agenda">안건/목적</label>
        <textarea id="mf-agenda" value={meta.agenda ?? ""}
          onChange={(e) => setMeta("agenda", e.target.value)} />
      </div>
    </div>
  );
}
