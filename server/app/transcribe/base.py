from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

from pydantic import BaseModel


class TranscriptSegment(BaseModel):
    speaker: str
    start_ms: int
    end_ms: int
    text: str


class TranscriptResult(BaseModel):
    segments: list[TranscriptSegment]
    full_text: str
    language: str

    def to_dict(self) -> dict:
        return self.model_dump()


@runtime_checkable
class Transcriber(Protocol):
    def transcribe(self, audio_path: Path, language: Optional[str] = None) -> TranscriptResult: ...
