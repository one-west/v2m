import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RecordingList } from "./RecordingList";
import type { RecordingSummary } from "../../lib/types";

const rows: RecordingSummary[] = [
  { id: "a", title: "주간회의", status: "done", created_at: "x", duration_sec: 60,
    meta: { date: "2026-06-23", attendees: "홍길동, 김철수" } },
  { id: "b", title: "스프린트", status: "transcribing", created_at: "y", duration_sec: null, meta: null },
];

describe("RecordingList", () => {
  it("shows empty state", () => {
    render(<RecordingList recordings={[]} onSelect={vi.fn()} onDelete={vi.fn()} />);
    expect(screen.getByText("아직 회의가 없습니다.")).toBeInTheDocument();
  });

  it("renders rows + sub text and fires select/delete", async () => {
    const onSelect = vi.fn();
    const onDelete = vi.fn();
    render(<RecordingList recordings={rows} onSelect={onSelect} onDelete={onDelete} />);
    expect(screen.getByText("완료")).toBeInTheDocument();
    expect(screen.getByText(/참석 2명/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "주간회의" }));
    expect(onSelect).toHaveBeenCalledWith("a");
    await userEvent.click(screen.getByRole("button", { name: "스프린트 삭제" }));
    expect(onDelete).toHaveBeenCalledWith("b");
  });

  it("selects when clicking the row body (sub text), not only the title", async () => {
    const onSelect = vi.fn();
    render(<RecordingList recordings={rows} onSelect={onSelect} onDelete={vi.fn()} />);
    await userEvent.click(screen.getByText(/참석 2명/));
    expect(onSelect).toHaveBeenCalledWith("a");
  });
});
