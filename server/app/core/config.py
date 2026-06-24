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
    # Optional dir containing ffmpeg.exe, prepended to PATH at transcribe time.
    # Use when ffmpeg is installed but not on the system PATH (e.g. winget on Windows).
    ffmpeg_dir: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
