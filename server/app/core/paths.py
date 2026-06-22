import os
from pathlib import Path


def get_data_dir() -> Path:
    override = os.environ.get("V2M_DATA_DIR")
    if override:
        base = Path(override)
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "v2m"
    else:
        base = Path.home() / ".local/share/v2m"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _ensure(sub: str) -> Path:
    p = get_data_dir() / sub
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_audio_dir() -> Path:
    return _ensure("audio")


def get_models_dir() -> Path:
    return _ensure("models")


def get_logs_dir() -> Path:
    return _ensure("logs")


def get_db_path() -> Path:
    _ensure("db")
    return get_data_dir() / "db" / "v2m.db"
