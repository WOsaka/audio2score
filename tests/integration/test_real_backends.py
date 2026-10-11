import importlib.util

import numpy as np
import pytest

from audio2score.model import NoteList
from audio2score.transcribe import get_transcriber

pytestmark = pytest.mark.slow


def synth_clip(sr=16_000, dur=6.0) -> np.ndarray:
    """Sechs Sekunden Klavier-ähnlicher Klang: Melodie C-E-G, dann C-Dur-Akkord."""
    y = np.zeros(int(sr * dur), dtype=np.float32)

    def tone(midi, onset, length):
        f = 440 * 2 ** ((midi - 69) / 12)
        t = np.arange(int(length * sr)) / sr
        s = sum(a * np.sin(2 * np.pi * f * k * t) for k, a in enumerate([1, 0.5, 0.3, 0.2], 1))
        s = s * np.exp(-2.5 * t) * np.minimum(1, t / 0.005)
        i = int(onset * sr)
        y[i : i + len(s)] += s[: len(y) - i].astype(np.float32)

    for midi, onset in [(60, 0.5), (64, 1.5), (67, 2.5)]:
        tone(midi, onset, 2.0)
    for midi in (48, 55, 64):
        tone(midi, 4.0, 2.0)
    return y / np.abs(y).max() * 0.9


@pytest.mark.parametrize(
    "backend",
    [
        "bytedance",
        pytest.param(
            "basic-pitch",
            marks=pytest.mark.skipif(
                importlib.util.find_spec("basic_pitch") is None, reason="basic-pitch fehlt"
            ),
        ),
    ],
)
def test_backend_runs_on_cpu_and_finds_the_melody(backend):
    nl = get_transcriber(backend).transcribe(synth_clip(), 16_000)
    assert isinstance(nl, NoteList)
    assert nl.duration == pytest.approx(6.0)
    found = {(n.pitch, round(n.onset, 1)) for n in nl.notes}
    for pitch, onset in [(60, 0.5), (64, 1.5), (67, 2.5)]:
        assert any(p == pitch and abs(o - onset) <= 0.1 for p, o in found), (pitch, onset)
