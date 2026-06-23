# V2M Server

Local FastAPI backend: meeting audio → local WhisperX transcription
(speaker diarization + timestamps) → transcript + claude.ai prompt bundle.

## Prerequisites
1. Python 3.11+
2. Install dependencies: `pip install -e ".[dev]"` (CPU-only, no torch/whisperx in tests)
3. For real transcription install ML extras: `pip install -e ".[ml]"` — requires ffmpeg
   and ensure it is on PATH.
4. Copy `.env.example` to `.env`. Set `V2M_HF_TOKEN` (accept terms for
   `pyannote/segmentation-3.0` and `pyannote/speaker-diarization-3.1` on Hugging Face first).

## Run
`python run.py` → open `http://127.0.0.1:8000`

## Test
`python -m pytest -v` (tests use a fake transcriber; torch/whisperx not required)

Data (db, audio, models, logs) is stored under `%LOCALAPPDATA%\v2m\`.
