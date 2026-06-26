from pathlib import Path
from typing import Optional

from app.transcribe.base import StageCallback, TranscriptResult, TranscriptSegment

_DEFAULT = TranscriptResult(
    segments=[
        TranscriptSegment(speaker="SPEAKER_00", start_ms=0, end_ms=3000, text="회의를 시작하겠습니다."),
        TranscriptSegment(speaker="SPEAKER_01", start_ms=3200, end_ms=6000, text="네, 좋습니다."),
    ],
    full_text="회의를 시작하겠습니다. 네, 좋습니다.",
    language="ko",
)


class FakeTranscriber:
    def __init__(self, result: Optional[TranscriptResult] = None) -> None:
        self._result = result or _DEFAULT
        self.last_audio_path: Optional[Path] = None
        self.last_language: Optional[str] = None
        self.stages: list[str] = []

    def transcribe(self, audio_path: Path, language: Optional[str] = None,
                   on_stage: StageCallback = None) -> TranscriptResult:
        self.last_audio_path = audio_path
        self.last_language = language
        if on_stage:
            on_stage("transcribing")
            self.stages.append("transcribing")
        return self._result
