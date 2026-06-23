import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CopyForClaude } from "./CopyForClaude";

vi.mock("../../lib/api", () => ({ getPrompt: vi.fn() }));
import { getPrompt } from "../../lib/api";

const writeText = vi.fn().mockResolvedValue(undefined);

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("navigator", { clipboard: { writeText } });
  vi.stubGlobal("open", vi.fn());
});

describe("CopyForClaude", () => {
  it("copies the prompt and confirms", async () => {
    (getPrompt as ReturnType<typeof vi.fn>).mockResolvedValue({
      prompt: "PROMPT-TEXT", transcript_text: "t", char_count: 12, too_long: false,
    });
    render(<CopyForClaude id="a" />);
    await userEvent.click(screen.getByRole("button", { name: /복사/ }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("PROMPT-TEXT"));
    expect(screen.getByRole("status")).toHaveTextContent(/복사되었습니다/);
    expect(window.open).toHaveBeenCalledWith("https://claude.ai/new", "_blank", "noopener");
  });

  it("warns when too long", async () => {
    (getPrompt as ReturnType<typeof vi.fn>).mockResolvedValue({
      prompt: "x", transcript_text: "t", char_count: 99999, too_long: true,
    });
    render(<CopyForClaude id="a" />);
    await userEvent.click(screen.getByRole("button", { name: /복사/ }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/한도/));
  });
});
