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


def transcode_to_mp3(src: Path, dst: Path, exe: str) -> None:
    """Encode `src` to MP3 at `dst`. Raises RuntimeError if ffmpeg fails."""
    proc = subprocess.run(
        [exe, "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
         "-vn", "-c:a", "libmp3lame", "-q:a", "4", str(dst)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"ffmpeg exited {proc.returncode}")
