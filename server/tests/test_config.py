from app.core.config import Settings


def test_defaults():
    s = Settings(_env_file=None)
    assert s.whisper_model == "medium"
    assert s.host == "127.0.0.1"
    assert s.port == 8000
    assert s.language == "ko"
    assert s.hf_token == ""


def test_env_override(monkeypatch):
    monkeypatch.setenv("V2M_WHISPER_MODEL", "small")
    monkeypatch.setenv("V2M_PORT", "9001")
    s = Settings(_env_file=None)
    assert s.whisper_model == "small"
    assert s.port == 9001


def test_get_settings_is_cached():
    from app.core.config import get_settings
    assert get_settings() is get_settings()
