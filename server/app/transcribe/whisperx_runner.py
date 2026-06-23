from pathlib import Path

from app.transcribe.base import TranscriptResult, TranscriptSegment


class WhisperXTranscriber:
    """Real local STT + diarization. whisperx/torch imported lazily."""

    def __init__(self, model_size: str, hf_token: str, device: str = "cpu",
                 compute_type: str = "int8") -> None:
        self.model_size = model_size
        self.hf_token = hf_token
        self.device = device
        self.compute_type = compute_type

    def transcribe(self, audio_path: Path) -> TranscriptResult:
        import os

        # Windows: HuggingFace cache uses symlinks, which need Developer Mode or admin.
        # Without this, model downloads fail with WinError 1314. Copy files instead.
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")

        import whisperx  # lazy: keeps torch out of test imports

        from app.core.paths import get_models_dir

        model = whisperx.load_model(
            self.model_size, self.device, compute_type=self.compute_type,
            download_root=str(get_models_dir()),
        )
        audio = whisperx.load_audio(str(audio_path))
        result = model.transcribe(audio)
        language = result.get("language", "ko")

        align_model, metadata = whisperx.load_align_model(language_code=language, device=self.device)
        aligned = whisperx.align(result["segments"], align_model, metadata, audio, self.device)

        from whisperx.diarize import DiarizationPipeline  # moved out of top-level in whisperx 3.2+

        # Pin to whisperx's current default diarization model. Users must accept its
        # gated terms once at https://huggingface.co/pyannote/speaker-diarization-community-1
        diarize_model = DiarizationPipeline(
            model_name="pyannote/speaker-diarization-community-1",
            token=self.hf_token,
            device=self.device,
        )
        diarize_segments = diarize_model(audio)
        final = whisperx.assign_word_speakers(diarize_segments, aligned)

        segments: list[TranscriptSegment] = []
        texts: list[str] = []
        for seg in final.get("segments", []):
            text = seg.get("text", "").strip()
            if not text:
                continue
            segments.append(TranscriptSegment(
                speaker=seg.get("speaker", "SPEAKER_00"),
                start_ms=int(seg.get("start", 0) * 1000),
                end_ms=int(seg.get("end", 0) * 1000),
                text=text,
            ))
            texts.append(text)
        return TranscriptResult(segments=segments, full_text=" ".join(texts), language=language)
