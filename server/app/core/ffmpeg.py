"""Locating and driving the ffmpeg CLI.

whisperx shells out to ffmpeg itself (it only needs it on PATH), while the audio
endpoint invokes it directly — hence one shared place that answers "where is it".
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

_EXE = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"


def find_ffmpeg(ffmpeg_dir: str = "") -> Optional[str]:
    """Path to the ffmpeg executable, or None when it isn't installed.

    Prefers the configured V2M_FFMPEG_DIR (winget and similar installs often
    aren't on PATH), then falls back to a normal PATH lookup.
    """
    if ffmpeg_dir:
        candidate = Path(ffmpeg_dir) / _EXE
        if candidate.is_file():
            return str(candidate)
    return shutil.which("ffmpeg")


def _run(exe: str, args: list[str]) -> None:
    proc = subprocess.run([exe, "-hide_banner", "-loglevel", "error", "-y", *args],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"ffmpeg exited {proc.returncode}")


def transcode_to_mp3(src: Path, dst: Path, exe: str) -> None:
    """Encode `src` to MP3 at `dst`. Raises RuntimeError if ffmpeg fails."""
    _run(exe, ["-i", str(src), "-vn", "-c:a", "libmp3lame", "-q:a", "4", str(dst)])


def remux_webm(src: Path, dst: Path, exe: str) -> None:
    """Rewrite `src` into a seekable WebM at `dst` without re-encoding.

    MediaRecorder streams its output live and never writes a duration into the
    container, so browsers report `duration === Infinity` and refuse to seek.
    Copying the streams into a finalized file restores it — ~0.3s for a 68 MB,
    74-minute recording, since no audio is decoded.
    """
    _run(exe, ["-i", str(src), "-c", "copy", str(dst)])


def probe_duration(path: Path, exe: str) -> Optional[float]:
    """Container duration in seconds, or None when it has none / can't be read.

    Uses the ffprobe sitting next to the given ffmpeg.
    """
    probe = Path(exe).with_name(_EXE.replace("ffmpeg", "ffprobe"))
    proc = subprocess.run(
        [str(probe) if probe.is_file() else "ffprobe", "-hide_banner", "-loglevel", "error",
         "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    )
    out = proc.stdout.strip()
    if proc.returncode != 0 or out in ("", "N/A"):
        return None
    try:
        return float(out)
    except ValueError:
        return None
