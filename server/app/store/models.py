from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from sqlalchemy import Column
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


class RecordingStatus(str, Enum):
    RECORDED = "recorded"
    TRANSCRIBING = "transcribing"
    DONE = "done"
    FAILED = "failed"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Recording(SQLModel, table=True):
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    title: str
    created_at: datetime = Field(default_factory=_now)
    duration_sec: Optional[int] = None
    audio_path: str
    status: RecordingStatus = Field(default=RecordingStatus.RECORDED)
    error: Optional[str] = None
    transcript: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    meta: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    # Per-recording transcription language: "ko"/"en"/… to force, "auto" to detect,
    # None for older rows (transcriber falls back to the configured V2M_LANGUAGE).
    language: Optional[str] = Field(default=None)
    # Coarse transcription progress while status == transcribing:
    # loading | transcribing | aligning | diarizing (None otherwise).
    stage: Optional[str] = Field(default=None)
