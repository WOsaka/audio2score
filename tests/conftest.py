import numpy as np
import pytest
import soundfile as sf


def sine(freq: float, dur: float, sr: int, amp: float = 0.5) -> np.ndarray:
    t = np.arange(int(sr * dur)) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


@pytest.fixture
def make_wav(tmp_path):
    """Schreibt eine Sinus-WAV/FLAC (Stereo, 44,1 kHz) und gibt den Pfad zurück."""

    def _make(name="a.wav", sr=44_100, dur=1.0, channels=2, amp=0.5):
        y = sine(440.0, dur, sr, amp)
        data = np.stack([y] * channels, axis=1) if channels > 1 else y
        path = tmp_path / name
        sf.write(path, data, sr)
        return path

    return _make
