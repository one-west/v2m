import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RecordingList } from "./RecordingList";
import type { RecordingSummary } from "../../lib/types";

const rows: RecordingSummary[] = [
  { id: "a", title: "주간회의", status: "done", created_at: "2026-06-22T01:00:00", duration_sec: 60 },
  { id: "b", title: "스프린트", status: "transcribing", created_at: "2026-06-22T02:00:00", duration_sec: null },
];

describe("RecordingList", () => {
  it("shows empty state", () => {
    render(<RecordingList recordings={[]} onSelect={vi.fn()} onDelete={vi.fn()} />);
    expect(screen.getByText("아직 녹음이 없습니다.")).toBeInTheDocument();
  });

  it("renders rows with status labels and fires select/delete", async () => {
    const onSelect = vi.fn();
    const onDelete = vi.fn();
    render(<RecordingList recordings={rows} onSelect={onSelect} onDelete={onDelete} />);
    expect(screen.getByText("완료")).toBeInTheDocument();
    expect(screen.getByText("전사 중")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "주간회의" }));
    expect(onSelect).toHaveBeenCalledWith("a");

    await userEvent.click(screen.getByRole("button", { name: "스프린트 삭제" }));
    expect(onDelete).toHaveBeenCalledWith("b");
  });
});
