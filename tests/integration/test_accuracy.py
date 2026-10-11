"""Genauigkeit gegen MAESTRO-Referenzen: Note-F1 (Onset ±50 ms, Offsets ignoriert) ≥ 0,90.

Erwartet Paare `<name>.wav` + `<name>.midi` (oder `.mid`) in data/testset/maestro/.
Ohne Daten wird der Test übersprungen.
"""

from pathlib import Path

import mir_eval
import numpy as np
import pretty_midi
import pytest

from audio2score.model import Note
from audio2score.pipeline import transcribe_file

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "testset" / "maestro"
MIN_F1 = 0.90


def note_f1(reference: list[Note], estimate: list[Note]) -> float:
    def arrays(notes):
        intervals = np.array([[n.onset, n.offset] for n in notes]).reshape(-1, 2)
        hz = np.array([pretty_midi.note_number_to_hz(n.pitch) for n in notes])
        return intervals, hz

    ref_i, ref_p = arrays(reference)
    est_i, est_p = arrays(estimate)
    _, _, f1, _ = mir_eval.transcription.precision_recall_f1_overlap(
        ref_i, ref_p, est_i, est_p, onset_tolerance=0.05, offset_ratio=None
    )
    return f1


def read_reference(path: Path) -> list[Note]:
    midi = pretty_midi.PrettyMIDI(str(path))
    return [
        Note(n.pitch, n.start, n.end, max(n.velocity, 1))
        for inst in midi.instruments
        if not inst.is_drum
        for n in inst.notes
        if 21 <= n.pitch <= 108 and n.end > n.start
    ]


def test_note_f1_helper():
    notes = [Note(60, 0.0, 1.0, 80), Note(64, 1.0, 2.0, 80)]
    assert note_f1(notes, notes) == 1.0
    shifted = [Note(60, 0.2, 1.2, 80), Note(64, 1.0, 2.0, 80)]  # erster Onset 200 ms daneben
    assert note_f1(notes, shifted) == pytest.approx(0.5)
    assert note_f1(notes, []) == 0.0


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
        pytest.skip(f"keine MAESTRO-Paare (wav + midi) in {DATA_DIR}")
    for wav, ref in pairs:
        result = transcribe_file(wav)
        f1 = note_f1(read_reference(ref), result.notelist.notes)
        assert f1 >= MIN_F1, f"{wav.name}: Note-F1 {f1:.3f} < {MIN_F1}"
