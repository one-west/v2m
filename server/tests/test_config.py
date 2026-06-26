from app.core.config import Settings


def test_defaults():
    s = Settings(_env_file=None)
    assert s.whisper_model == "medium"
    assert s.host == "127.0.0.1"
    assert s.port == 8000
    assert s.language == "ko"
    assert s.hf_token == ""
    assert s.batch_size == 16
    assert s.cpu_threads == 0
    assert s.suppress_numerals is True
    assert s.initial_prompt == ""


def test_env_override(monkeypatch):
    monkeypatch.setenv("V2M_WHISPER_MODEL", "small")
    monkeypatch.setenv("V2M_PORT", "9001")
    monkeypatch.setenv("V2M_BATCH_SIZE", "8")
    monkeypatch.setenv("V2M_CPU_THREADS", "6")
    monkeypatch.setenv("V2M_SUPPRESS_NUMERALS", "false")
    monkeypatch.setenv("V2M_INITIAL_PROMPT", "분기 실적 회의")
    s = Settings(_env_file=None)
    assert s.whisper_model == "small"
    assert s.port == 9001
    assert s.batch_size == 8
    assert s.cpu_threads == 6
    assert s.suppress_numerals is False
    assert s.initial_prompt == "분기 실적 회의"


def test_get_settings_is_cached():
    from app.core.config import get_settings
    assert get_settings() is get_settings()
