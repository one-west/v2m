import { describe, it, expect } from "vitest";
import { msToMmss, statusLabel, attendeesCount, languageLabel, stageLabel } from "./format";

describe("format", () => {
  it("formats ms as mm:ss", () => {
    expect(msToMmss(0)).toBe("00:00");
    expect(msToMmss(65000)).toBe("01:05");
    expect(msToMmss(3599000)).toBe("59:59");
  });

  it("maps status to Korean labels", () => {
    expect(statusLabel("recorded")).toBe("대기");
    expect(statusLabel("transcribing")).toBe("전사중");
    expect(statusLabel("done")).toBe("완료");
    expect(statusLabel("failed")).toBe("실패");
  });

  it("counts comma-separated attendees", () => {
    expect(attendeesCount(null)).toBe(0);
    expect(attendeesCount({ attendees: "홍길동, 김철수 ,  " })).toBe(2);
    expect(attendeesCount({})).toBe(0);
  });

  it("maps language codes to labels", () => {
    expect(languageLabel("ko")).toBe("한국어");
    expect(languageLabel("en")).toBe("English");
    expect(languageLabel("auto")).toBe("자동 감지");
    expect(languageLabel(null)).toBeNull();
    expect(languageLabel("fr")).toBe("fr"); // unknown -> passthrough
  });

  it("maps transcription stages to labels", () => {
    expect(stageLabel("loading")).toBe("모델 로딩");
    expect(stageLabel("transcribing")).toBe("음성 인식");
    expect(stageLabel("aligning")).toBe("정렬");
    expect(stageLabel("diarizing")).toBe("화자 분리");
    expect(stageLabel(null)).toBeNull();
  });
});
