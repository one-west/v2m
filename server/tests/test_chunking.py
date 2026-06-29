import numpy as np

from app.transcribe.chunking import plan_chunk_windows


def test_short_audio_returns_single_window():
    audio = np.ones(50, dtype=np.float32)
    assert plan_chunk_windows(audio, sample_rate=100, chunk_sec=1) == [(0, 50)]


def test_audio_exactly_one_chunk_is_single_window():
    audio = np.ones(100, dtype=np.float32)
    assert plan_chunk_windows(audio, sample_rate=100, chunk_sec=1) == [(0, 100)]


def test_zero_chunk_sec_returns_single_window():
    audio = np.ones(500, dtype=np.float32)
    assert plan_chunk_windows(audio, sample_rate=100, chunk_sec=0) == [(0, 500)]


def test_cuts_at_quiet_point_and_covers_contiguously():
    sr = 100
    audio = np.ones(250, dtype=np.float32)
    # quiet dips near the 100- and 200-sample chunk boundaries
    audio[88:96] = 0.0
    audio[188:196] = 0.0
    windows = plan_chunk_windows(audio, sample_rate=sr, chunk_sec=1, search_sec=0.3)

    # full, contiguous, gap-free, non-overlapping coverage
    assert windows[0][0] == 0
    assert windows[-1][1] == 250
    for (a, b), (c, d) in zip(windows, windows[1:]):
        assert b == c
    # the first cut lands inside the first quiet dip (not at the hard 100 mark)
    first_cut = windows[0][1]
    assert 88 <= first_cut < 96
    # more than one window for >1-chunk audio
    assert len(windows) >= 2
