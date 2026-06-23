import { useState } from "react";
import { getPrompt } from "../../lib/api";

const CLAUDE_URL = "https://claude.ai/new";

export function CopyForClaude({ id }: { id: string }) {
  const [state, setState] = useState<"idle" | "copied" | "error">("idle");
  const [tooLong, setTooLong] = useState(false);
  const [charCount, setCharCount] = useState<number | null>(null);

  async function handleCopy() {
    try {
      const bundle = await getPrompt(id);
      await navigator.clipboard.writeText(bundle.prompt);
      setTooLong(bundle.too_long);
      setCharCount(bundle.char_count);
      setState("copied");
      window.open(CLAUDE_URL, "_blank", "noopener");
    } catch {
      setState("error");
    }
  }

  return (
    <div className="copy-for-claude">
      <button onClick={handleCopy}>전사본 + 프롬프트 복사 후 claude.ai 열기</button>
      {state === "copied" && (
        <p role="status">
          복사되었습니다. claude.ai에 붙여넣으세요.
          {charCount !== null && ` (${charCount.toLocaleString()}자)`}
        </p>
      )}
      {tooLong && (
        <p role="alert">전사본이 길어 claude.ai 입력 한도를 넘을 수 있습니다. 나눠서 붙여넣으세요.</p>
      )}
      {state === "error" && <p role="alert">복사에 실패했습니다.</p>}
    </div>
  );
}
