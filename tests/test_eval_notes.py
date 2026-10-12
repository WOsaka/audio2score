import pretty_midi
import pytest

from audio2score.eval.notes import note_f1, note_prf, read_midi_notes
from audio2score.model import Note


def test_note_f1_perfect_shifted_and_empty():
    notes = [Note(60, 0.0, 1.0, 80), Note(64, 1.0, 2.0, 80)]
    assert note_f1(notes, notes) == 1.0
    shifted = [Note(60, 0.2, 1.2, 80), Note(64, 1.0, 2.0, 80)]  # erster Onset 200 ms daneben
    assert note_f1(notes, shifted) == pytest.approx(0.5)
    assert note_f1(notes, []) == 0.0


def test_note_prf_precision_and_recall_differ():
    ref = [Note(60, 0.0, 1.0, 80), Note(64, 1.0, 2.0, 80)]
    est = [Note(60, 0.0, 1.0, 80), Note(67, 3.0, 4.0, 80), Note(69, 5.0, 6.0, 80)]
    p, r, f1 = note_prf(ref, est)
    assert p == pytest.approx(1 / 3)
    assert r == pytest.approx(1 / 2)
    assert f1 == pytest.approx(0.4)


def test_read_midi_notes_filters_drums_and_out_of_range(tmp_path):
    midi = pretty_midi.PrettyMIDI()
    piano = pretty_midi.Instrument(program=0)
    piano.notes += [
        pretty_midi.Note(80, 60, 0.0, 1.0),
        pretty_midi.Note(80, 10, 0.0, 1.0),  # unter A0
        pretty_midi.Note(1, 62, 1.0, 2.0),
    ]
    drums = pretty_midi.Instrument(program=0, is_drum=True)
    drums.notes.append(pretty_midi.Note(80, 36, 0.0, 1.0))
    midi.instruments += [piano, drums]
    path = tmp_path / "a.mid"
    midi.write(str(path))
    notes = read_midi_notes(path)
    assert [(n.pitch, n.velocity) for n in notes] == [(60, 80), (62, 1)]
