from app.core.config import Settings


def check_models_ready(settings: Settings) -> bool:
    """Whether transcription can run without further one-time setup.

    Only diarization pulls a gated HuggingFace model, so fast mode
    (V2M_DIARIZE=false) is ready with no token at all.
    """
    return bool(settings.hf_token) or not settings.diarize
