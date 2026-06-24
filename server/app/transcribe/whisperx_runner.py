import threading
import time
from pathlib import Path

from app.transcribe.base import TranscriptResult, TranscriptSegment


class WhisperXTranscriber:
    """Real local STT + diarization. whisperx/torch imported lazily.

    The STT model, per-language align models, and the diarization pipeline are
    loaded once and cached on the instance — create_app builds a single
    long-lived transcriber, so every recording after the first skips the (slow)
    model-load step.
    """

    def __init__(self, model_size: str, hf_token: str, device: str = "cpu",
                 compute_type: str = "int8", ffmpeg_dir: str = "",
                 batch_size: int = 16, cpu_threads: int = 0) -> None:
        self.model_size = model_size
        self.hf_token = hf_token
        self.device = device
        self.compute_type = compute_type
        self.ffmpeg_dir = ffmpeg_dir
        self.batch_size = batch_size
        self.cpu_threads = cpu_threads
        self._model = None
        self._align_cache: dict[str, tuple] = {}
        self._diarize = None
        self._lock = threading.Lock()

    def _get_model(self):
        if self._model is None:
            import whisperx  # lazy: keeps torch out of test imports

            from app.core.paths import get_models_dir
            with self._lock:
                if self._model is None:
                    self._model = whisperx.load_model(
                        self.model_size, self.device, compute_type=self.compute_type,
                        threads=self.cpu_threads, download_root=str(get_models_dir()),
                    )
        return self._model

    def _get_align(self, language: str):
        cached = self._align_cache.get(language)
        if cached is None:
            import whisperx
            with self._lock:
                cached = self._align_cache.get(language)
                if cached is None:
                    cached = whisperx.load_align_model(language_code=language, device=self.device)
                    self._align_cache[language] = cached
        return cached

    def _get_diarize(self):
        if self._diarize is None:
            # moved out of top-level in whisperx 3.2+
            from whisperx.diarize import DiarizationPipeline
            with self._lock:
                if self._diarize is None:
                    # Pin to whisperx's current default diarization model. Users must accept
                    # its gated terms once at
                    # https://huggingface.co/pyannote/speaker-diarization-community-1
                    self._diarize = DiarizationPipeline(
                        model_name="pyannote/speaker-diarization-community-1",
                        token=self.hf_token,
                        device=self.device,
                    )
        return self._diarize

    def transcribe(self, audio_path: Path) -> TranscriptResult:
        import os

        # Windows: HuggingFace cache uses symlinks, which need Developer Mode or admin.
        # Without this, model downloads fail with WinError 1314. Copy files instead.
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")

        # Make ffmpeg discoverable if it is installed somewhere off the system PATH.
        if self.ffmpeg_dir:
            os.environ["PATH"] = self.ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")

        import whisperx  # lazy: keeps torch out of test imports

        t0 = time.perf_counter()
        model = self._get_model()  # cached after the first recording
        audio = whisperx.load_audio(str(audio_path))
        t_load = time.perf_counter()
        # batch_size is WhisperX's core speedup: VAD-chunked segments run in parallel.
        result = model.transcribe(audio, batch_size=self.batch_size)
        language = result.get("language", "ko")
        t_stt = time.perf_counter()

        align_model, metadata = self._get_align(language)  # cached per language
        aligned = whisperx.align(result["segments"], align_model, metadata, audio, self.device)
        t_align = time.perf_counter()

        diarize_model = self._get_diarize()  # cached after the first recording
        diarize_segments = diarize_model(audio)
        final = whisperx.assign_word_speakers(diarize_segments, aligned)
        t_diar = time.perf_counter()

        print(
            f"[v2m.transcribe] model={self.model_size} batch={self.batch_size} "
            f"threads={self.cpu_threads or 'auto'} lang={language} | "
            f"load+decode={t_load - t0:.1f}s stt={t_stt - t_load:.1f}s "
            f"align={t_align - t_stt:.1f}s diarize={t_diar - t_align:.1f}s "
            f"total={t_diar - t0:.1f}s",
            flush=True,
        )

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
