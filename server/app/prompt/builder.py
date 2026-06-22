from pydantic import BaseModel

INSTRUCTION = (
    "당신은 회의록 작성 전문가입니다. 아래 화자별·타임스탬프 전사본을 바탕으로 "
    "정형화된 한국어 회의록을 작성하세요. 다음 4개 항목으로 구성합니다:\n"
    "1. 요약 (핵심 내용 3~5문장)\n"
    "2. 핵심 논의 (주제별 불릿)\n"
    "3. 결정사항 (합의된 사항)\n"
    "4. 액션아이템 (할 일 — 담당자/기한이 언급되면 함께 표기)\n\n"
    "=== 전사본 ===\n"
)


class PromptBundle(BaseModel):
    prompt: str
    transcript_text: str
    char_count: int
    too_long: bool


def _ms_to_mmss(ms: int) -> str:
    total = ms // 1000
    return f"{total // 60:02d}:{total % 60:02d}"


def format_transcript(transcript: dict) -> str:
    lines: list[str] = []
    last_speaker = None
    for seg in transcript.get("segments", []):
        if seg["speaker"] != last_speaker:
            lines.append(f"[{_ms_to_mmss(seg['start_ms'])}] {seg['speaker']}:")
            last_speaker = seg["speaker"]
        lines.append(f"  {seg['text']}")
    return "\n".join(lines)


def build_prompt(transcript: dict, *, too_long_threshold: int = 40000) -> PromptBundle:
    transcript_text = format_transcript(transcript)
    prompt = INSTRUCTION + transcript_text
    return PromptBundle(
        prompt=prompt,
        transcript_text=transcript_text,
        char_count=len(prompt),
        too_long=len(prompt) > too_long_threshold,
    )
