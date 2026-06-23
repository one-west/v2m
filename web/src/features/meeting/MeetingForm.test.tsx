import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MeetingForm } from "./MeetingForm";

describe("MeetingForm", () => {
  it("renders fields and emits changes", async () => {
    const onChange = vi.fn();
    render(<MeetingForm title="" meta={{}} onChange={onChange} />);
    expect(screen.getByLabelText("제목")).toBeInTheDocument();
    expect(screen.getByLabelText("장소")).toBeInTheDocument();
    expect(screen.getByLabelText("참석자")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("장소"), "A");
    expect(onChange).toHaveBeenLastCalledWith({ title: "", meta: { location: "A" } });
  });

  it("shows existing values", () => {
    render(<MeetingForm title="주간회의" meta={{ location: "B룸" }} onChange={vi.fn()} />);
    expect(screen.getByLabelText("제목")).toHaveValue("주간회의");
    expect(screen.getByLabelText("장소")).toHaveValue("B룸");
  });
});
