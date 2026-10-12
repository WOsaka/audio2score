"""Note-F1 (Onset ±50 ms, Offsets ignoriert) und Referenz-MIDI lesen."""

from pathlib import Path

import mir_eval
import numpy as np
import pretty_midi

from audio2score.model import PITCH_MAX, PITCH_MIN, Note

ONSET_TOLERANCE = 0.05


def note_prf(reference: list[Note], estimate: list[Note]) -> tuple[float, float, float]:
    """(Precision, Recall, F1)."""

    def arrays(notes):
        intervals = np.array([[n.onset, n.offset] for n in notes]).reshape(-1, 2)
        hz = np.array([pretty_midi.note_number_to_hz(n.pitch) for n in notes])
        return intervals, hz

    ref_i, ref_p = arrays(reference)
    est_i, est_p = arrays(estimate)
    p, r, f1, _ = mir_eval.transcription.precision_recall_f1_overlap(
        ref_i, ref_p, est_i, est_p, onset_tolerance=ONSET_TOLERANCE, offset_ratio=None
    )
    return p, r, f1


def note_f1(reference: list[Note], estimate: list[Note]) -> float:
    return note_prf(reference, estimate)[2]


def read_midi_notes(path: Path) -> list[Note]:
    midi = pretty_midi.PrettyMIDI(str(path))
    return [
        Note(n.pitch, n.start, n.end, max(n.velocity, 1))
        for inst in midi.instruments
        if not inst.is_drum
        for n in inst.notes
        if PITCH_MIN <= n.pitch <= PITCH_MAX and n.end > n.start
    ]
