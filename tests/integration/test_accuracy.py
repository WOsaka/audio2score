"""Genauigkeit gegen MAESTRO-Referenzen: Note-F1 (Onset ±50 ms, Offsets ignoriert) ≥ 0,90.

Erwartet Paare `<name>.wav` + `<name>.midi` (oder `.mid`) in data/testset/maestro/
(laden: `audio2score testset fetch --only <id>`). Ohne Daten wird der Test übersprungen.
"""

from pathlib import Path

import pytest

from audio2score.eval.notes import note_f1, read_midi_notes
from audio2score.pipeline import transcribe_file

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "testset" / "maestro"
MIN_F1 = 0.90


def _pairs():
    if not DATA_DIR.is_dir():
        return []
    pairs = []
    for wav in sorted(DATA_DIR.glob("*.wav")):
        ref = next(
            (p for p in (wav.with_suffix(".midi"), wav.with_suffix(".mid")) if p.is_file()), None
        )
        if ref:
            pairs.append((wav, ref))
    return pairs


@pytest.mark.slow
def test_note_f1_on_maestro():
    pairs = _pairs()
    if not pairs:
        pytest.skip(
            f"keine MAESTRO-Paare (wav + midi) in {DATA_DIR} - "
            "laden mit: audio2score testset fetch --only maestro-chopin-etude-10-9"
        )
    for wav, ref in pairs:
        result = transcribe_file(wav)
        f1 = note_f1(read_midi_notes(ref), result.notelist.notes)
        assert f1 >= MIN_F1, f"{wav.name}: Note-F1 {f1:.3f} < {MIN_F1}"
