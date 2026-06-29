"""Pure, torch-free helpers for splitting long audio into chunk windows.

Imports only numpy so it stays unit-testable without whisperx/torch.
"""

import numpy as np


def _quietest_point(audio: np.ndarray, lo: int, hi: int, frame: int) -> int:
    """Return the start sample of the lowest-RMS-energy frame in [lo, hi)."""
    best_idx = lo
    best_energy = None
    i = lo
    while i < hi:
        seg = audio[i:min(i + frame, hi)]
        energy = float(np.mean(seg * seg)) if seg.size else float("inf")
        if best_energy is None or energy < best_energy:
            best_energy = energy
            best_idx = i
        i += frame
    return best_idx


def plan_chunk_windows(audio, sample_rate, chunk_sec, search_sec=30):
    """Split `audio` into ~chunk_sec windows that cut on silence.

    Returns contiguous, gap-free (start_sample, end_sample) windows covering the
    whole array. Each interior cut is placed at the quietest frame within
    ±search_sec of the target boundary, so chunks split between utterances rather
    than mid-word. Audio at or shorter than one chunk returns a single window.
    """
    audio = np.asarray(audio, dtype=np.float32)
    n = len(audio)
    chunk = int(chunk_sec * sample_rate)
    if chunk <= 0 or n <= chunk:
        return [(0, n)]

    search = int(search_sec * sample_rate)
    frame = max(1, int(0.02 * sample_rate))  # 20 ms energy frames
    windows: list[tuple[int, int]] = []
    start = 0
    while start < n:
        target = start + chunk
        if target >= n:
            windows.append((start, n))
            break
        lo = max(start + 1, target - search)
        hi = min(n, target + search)
        cut = _quietest_point(audio, lo, hi, frame)
        windows.append((start, cut))
        start = cut
    return windows
