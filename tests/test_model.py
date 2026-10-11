import pytest

from audio2score.model import Note, NoteList, PedalEvent


def make_notelist() -> NoteList:
    return NoteList(
        notes=[Note(60, 0.5, 1.0, 80), Note(64, 0.5, 1.2, 70), Note(67, 1.0, 2.0, 90)],
        pedals=[PedalEvent(0.4, 2.1)],
        duration=3.0,
        backend="bytedance",
        backend_version="0.0.6+note_F1=0.9677",
    )


def test_dict_roundtrip():
    nl = make_notelist()
    assert NoteList.from_dict(nl.to_dict()) == nl


def test_json_roundtrip(tmp_path):
    nl = make_notelist()
    path = tmp_path / "sub" / "nl.json"
    nl.to_json(path)
    assert NoteList.from_json(path) == nl


def test_notes_sorted_on_construction():
    nl = NoteList(
        notes=[Note(67, 1.0, 2.0, 90), Note(64, 0.5, 1.2, 70), Note(60, 0.5, 1.0, 80)],
        pedals=[],
        duration=3.0,
        backend="x",
        backend_version="1",
    )
    assert [n.pitch for n in nl.notes] == [60, 64, 67]


def test_empty_notelist_roundtrip():
    nl = NoteList(notes=[], pedals=[], duration=0.0, backend="x", backend_version="1")
    assert NoteList.from_dict(nl.to_dict()) == nl


@pytest.mark.parametrize(
    "args",
    [
        (60, 1.0, 1.0, 80),  # offset == onset
        (60, 1.0, 0.5, 80),  # offset < onset
        (20, 0.0, 1.0, 80),  # Pitch zu tief
        (109, 0.0, 1.0, 80),  # Pitch zu hoch
        (60, 0.0, 1.0, 0),  # Velocity zu klein
        (60, 0.0, 1.0, 128),  # Velocity zu groß
        (60, -0.1, 1.0, 80),  # negativer Onset
    ],
)
def test_note_validation(args):
    with pytest.raises(ValueError):
        Note(*args)


def test_pedal_validation():
    with pytest.raises(ValueError):
        PedalEvent(2.0, 1.0)
