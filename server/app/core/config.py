from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="V2M_", env_file=".env", extra="ignore")

    hf_token: str = ""
    whisper_model: str = "medium"
    host: str = "127.0.0.1"
    port: int = 8000
    language: str = "ko"
    # WhisperX batched inference size (its key speedup); higher = faster but more RAM.
    batch_size: int = 16
    # ctranslate2 CPU threads; 0 = auto-detect all physical cores.
    cpu_threads: int = 0
    # Transcribe spoken numbers as words ("천만원") instead of digits — fewer
    # number misrecognitions in Korean meetings.
    suppress_numerals: bool = True
    # Optional decoder priming text (domain terms / spelling hints). Empty = none.
    initial_prompt: str = ""
    # Voice-activity detection backend: "silero" (fast, default) or "pyannote" (slower).
    # Only changes how speech regions are segmented, not transcription text quality.
    vad_method: str = "silero"
    # Speaker diarization + word alignment. These are ~90% of CPU time on long audio.
    # Set false ("fast mode") for a single-speaker, segment-timestamp transcript that
    # finishes ~10x faster — e.g. 1-hour lectures where speaker labels aren't needed.
    diarize: bool = True
    # Optional dir containing ffmpeg.exe, prepended to PATH at transcribe time.
    # Use when ffmpeg is installed but not on the system PATH (e.g. winget on Windows).
    ffmpeg_dir: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
