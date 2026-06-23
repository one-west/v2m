# V2M Server

Local FastAPI backend: meeting audio → local WhisperX transcription
(speaker diarization + timestamps) → transcript + claude.ai prompt bundle.

## Prerequisites
1. Python 3.11+ for the app + tests. **For real transcription use Python 3.11–3.12**:
   the ML stack (torch / ctranslate2 via whisperx) has no 3.13/3.14 wheels yet, so create
   a separate 3.12 venv for the `[ml]` extras.
2. Install dependencies: `pip install -e ".[dev]"` (CPU-only, no torch/whisperx in tests)
3. For real transcription install ML extras: `pip install -e ".[dev,ml]"` (Python 3.12 venv).
   Requires **ffmpeg** on PATH (whisperx decodes audio via the ffmpeg CLI).
4. Copy `.env.example` to `.env`. Set `V2M_HF_TOKEN`, and accept the gated terms for
   `pyannote/speaker-diarization-community-1` on Hugging Face first (the model whisperx uses).
   (Windows: the runner sets `HF_HUB_DISABLE_SYMLINKS=1` automatically so model downloads
   work without Developer Mode/admin.)

## Run
`python run.py` → open `http://127.0.0.1:8000`

## Test
`python -m pytest -v` (tests use a fake transcriber; torch/whisperx not required)

Data (db, audio, models, logs) is stored under `%LOCALAPPDATA%\v2m\`.
