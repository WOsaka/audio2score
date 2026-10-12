import pretty_midi
import pytest

from audio2score.export.midi import write_midi
from audio2score.model import Note, NoteList, PedalEvent


def nl(notes=(), pedals=()):
    return NoteList(list(notes), list(pedals), 5.0, "x", "1")


def test_notes_written_with_timing_and_velocity(tmp_path):
    out = tmp_path / "o.mid"
    write_midi(nl([Note(60, 0.5, 1.0, 80), Note(64, 1.0, 2.5, 33)]), out)
    inst = pretty_midi.PrettyMIDI(str(out)).instruments[0]
    assert inst.program == 0
    got = sorted((n.pitch, round(n.start, 2), round(n.end, 2), n.velocity) for n in inst.notes)
    assert got == [(60, 0.5, 1.0, 80), (64, 1.0, 2.5, 33)]


def test_pedal_written_as_cc64_pairs(tmp_path):
    out = tmp_path / "o.mid"
    write_midi(nl([Note(60, 0.5, 1.0, 80)], [PedalEvent(0.4, 2.0), PedalEvent(3.0, 4.0)]), out)
    ccs = [
        c for c in pretty_midi.PrettyMIDI(str(out)).instruments[0].control_changes if c.number == 64
    ]
    assert [(round(c.time, 2), c.value) for c in sorted(ccs, key=lambda c: c.time)] == [
        (0.4, 127),
        (2.0, 0),
        (3.0, 127),
        (4.0, 0),
    ]


def test_empty_list_gives_valid_file(tmp_path):
    out = tmp_path / "o.mid"
    write_midi(nl(), out)
    assert all(not i.notes for i in pretty_midi.PrettyMIDI(str(out)).instruments)


def test_output_dir_created(tmp_path):
    out = tmp_path / "a" / "b" / "o.mid"
    write_midi(nl([Note(60, 0.0, 1.0, 80)]), out)
    assert out.is_file()


def test_key_offsets_not_pedal_extended(tmp_path):
    out = tmp_path / "o.mid"
    write_midi(nl([Note(60, 0.0, 1.0, 80)], [PedalEvent(0.0, 3.0)]), out)
    note = pretty_midi.PrettyMIDI(str(out)).instruments[0].notes[0]
    assert note.end == pytest.approx(1.0, abs=0.01)
