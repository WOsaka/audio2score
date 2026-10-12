from dataclasses import replace

from audio2score.cleanup.notes import CleanupConfig, cleanup
from audio2score.model import Note, NoteList, PedalEvent


def nl(*notes, pedals=()):
    return NoteList(list(notes), list(pedals), 10.0, "x", "1")


def pitches(result):
    return [n.pitch for n in result.notes]


def test_removes_too_short_notes():
    result = cleanup(nl(Note(60, 1.0, 1.02, 80), Note(62, 1.0, 1.5, 80)))
    assert pitches(result) == [62]


def test_removes_notes_below_min_velocity():
    result = cleanup(nl(Note(60, 1.0, 2.0, 5), Note(62, 1.0, 2.0, 5), Note(64, 1.0, 2.0, 5)))
    assert result.notes == []  # absolut zu leise, obwohl alle gleich leise sind


def test_removes_notes_much_quieter_than_surroundings():
    loud = [Note(60 + i, 1.0 + i * 0.2, 2.0 + i * 0.2, 80) for i in range(5)]
    quiet = Note(40, 1.5, 2.5, 10)  # 10 < 0,2 * 80
    result = cleanup(nl(*loud, quiet))
    assert 40 not in pitches(result)
    assert len(result.notes) == 5


def test_keeps_quiet_passage_when_surroundings_are_quiet():
    quiet = [Note(60 + i, 1.0 + i * 0.2, 2.0 + i * 0.2, 12) for i in range(5)]
    assert len(cleanup(nl(*quiet)).notes) == 5


def test_relative_window_ignores_distant_loud_notes():
    far_loud = Note(80, 20.0, 21.0, 100)
    soft = [Note(60 + i, 1.0 + i * 0.2, 2.0 + i * 0.2, 12) for i in range(3)]
    result = cleanup(nl(*soft, far_loud))
    assert len(result.notes) == 4


def test_removes_octave_ghost():
    result = cleanup(nl(Note(60, 1.0, 2.0, 80), Note(72, 1.01, 2.0, 30)))
    assert pitches(result) == [60]


def test_keeps_octave_note_that_is_not_quiet_enough():
    result = cleanup(nl(Note(60, 1.0, 2.0, 80), Note(72, 1.0, 2.0, 50)))
    assert pitches(result) == [60, 72]


def test_keeps_quiet_octave_note_that_is_not_simultaneous():
    result = cleanup(nl(Note(60, 1.0, 2.0, 80), Note(72, 1.2, 2.0, 30)))
    assert pitches(result) == [60, 72]


def test_keeps_quiet_non_octave_note():
    result = cleanup(nl(Note(60, 1.0, 2.0, 80), Note(71, 1.0, 2.0, 30)))
    assert pitches(result) == [60, 71]


def test_ghost_checked_against_original_not_after_removals():
    # 84 ist Geist von 72, 72 ist Geist von 60: beide fallen
    result = cleanup(nl(Note(60, 1.0, 2.0, 80), Note(72, 1.0, 2.0, 30), Note(84, 1.0, 2.0, 10)))
    assert pitches(result) == [60]


def test_pedals_metadata_and_input_untouched():
    original = nl(Note(60, 1.0, 1.01, 80), pedals=[PedalEvent(0.5, 2.0)])
    result = cleanup(original)
    assert result.pedals == original.pedals
    assert (result.duration, result.backend, result.backend_version) == (10.0, "x", "1")
    assert len(original.notes) == 1  # Eingabe unverändert


def test_config_is_respected():
    cfg = replace(CleanupConfig(), min_duration=0.5)
    assert cleanup(nl(Note(60, 1.0, 1.2, 80)), cfg).notes == []


def test_empty_list():
    assert cleanup(nl()).notes == []
