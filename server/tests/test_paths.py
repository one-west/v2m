from pathlib import Path
from app.core import paths


def test_data_dir_honors_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("V2M_DATA_DIR", str(tmp_path / "v2m"))
    d = paths.get_data_dir()
    assert d == tmp_path / "v2m"
    assert d.is_dir()


def test_subdirs_are_created(tmp_path, monkeypatch):
    monkeypatch.setenv("V2M_DATA_DIR", str(tmp_path / "v2m"))
    assert paths.get_audio_dir().is_dir()
    assert paths.get_models_dir().is_dir()
    assert paths.get_logs_dir().is_dir()
    assert paths.get_db_path().name == "v2m.db"
    assert paths.get_db_path().parent.is_dir()
