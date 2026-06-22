from app.core.config import Settings


def check_models_ready(settings: Settings) -> bool:
    return bool(settings.hf_token)
