import pytest
from music21 import chord, clef, meter, note, stream, tempo

from audio2score.rhythm.meter import Grid, Meter
from audio2score.rhythm.quantize import QNote
from audio2score.score.build import build_score


def make_grid(num=4, den=4, bpb=None, spb=4, bars=4, pickup=0, bpm=120.0):
    bpb = bpb or num
    n_beats = bars * bpb + (pickup // spb) + 1
    times = [i * 0.5 for i in range(n_beats)]
    return Grid(Meter(num, den, bpb, spb, "given"), times, pickup // spb, pickup, bpm, 0.0)


def q(pitch, start, dur, vel=80):
    return QNote(pitch, start, dur, vel)


def measures(part):
    return list(part.getElementsByClass(stream.Measure))


def content(measure):
    return [e for e in measure.recurse().notesAndRests if e.activeSite is measure]


def rebuild(part):
    """(Tonhöhen, Start, Dauer) in Sechzehnteln; Haltebögen werden zusammengefasst."""
    out = []
    open_ = {}
    for m in measures(part):
        for el in content(m):
            if el.isRest:
                continue
            start = round((m.offset + el.offset) * 4)
            pitches = tuple(sorted(p.midi for p in el.pitches))
            tied = (
                el.tie.type in ("stop", "continue")
                if isinstance(el, note.Note) and el.tie
                else any(
                    n.tie and n.tie.type in ("stop", "continue") for n in getattr(el, "notes", [])
                )
            )
            length = round(el.duration.quarterLength * 4)
            if tied and pitches in open_:
                idx = open_[pitches]
                out[idx] = (pitches, out[idx][1], out[idx][2] + length)
            else:
                out.append((pitches, start, length))
                open_[pitches] = len(out) - 1
    return out


def test_two_staves_with_clefs_time_signature_and_metronome():
    score = build_score([q(72, 0, 4)], [q(48, 0, 4)], make_grid(3, 4, bars=2, bpm=92.4), "Titel")
    right, left = score.parts
    assert isinstance(right, stream.PartStaff) and isinstance(left, stream.PartStaff)
    assert right.recurse().getElementsByClass(clef.TrebleClef)
    assert left.recurse().getElementsByClass(clef.BassClef)
    assert right.recurse().getElementsByClass(meter.TimeSignature)[0].ratioString == "3/4"
    assert left.recurse().getElementsByClass(meter.TimeSignature)[0].ratioString == "3/4"
    marks = score.recurse().getElementsByClass(tempo.MetronomeMark)
    assert [m.number for m in marks] == [92]
    assert score.metadata.title == "Titel"


def test_every_measure_is_exactly_filled():
    notes = [q(72, 0, 3), q(74, 3, 5), q(76, 8, 1), q(77, 11, 7), q(79, 30, 2)]
    score = build_score(notes, [], make_grid(4, 4, bars=3), "t")
    for part in score.parts:
        ms = measures(part)
        assert len(ms) == 3
        for m in ms:
            assert sum(e.duration.quarterLength for e in content(m)) == pytest.approx(4.0)


def test_empty_hand_gets_whole_bar_rests():
    score = build_score([q(72, 0, 4)], [], make_grid(3, 4, bars=2), "t")
    left = score.parts[1]
    for m in measures(left):
        els = content(m)
        assert len(els) == 1 and els[0].isRest
        assert els[0].duration.quarterLength == 3.0


def test_note_over_the_barline_is_tied():
    score = build_score([q(72, 12, 8)], [], make_grid(4, 4, bars=2), "t")
    m1, m2 = measures(score.parts[0])
    first = [e for e in content(m1) if not e.isRest][0]
    second = [e for e in content(m2) if not e.isRest][0]
    assert first.tie.type == "start" and second.tie.type == "stop"
    assert first.pitch.midi == second.pitch.midi == 72
    assert first.duration.quarterLength == 1.0 and second.duration.quarterLength == 1.0


def test_unrepresentable_duration_is_split_into_tied_notes():
    score = build_score([q(72, 0, 5)], [], make_grid(4, 4, bars=1), "t")
    notes = [e for e in content(measures(score.parts[0])[0]) if not e.isRest]
    assert [e.duration.quarterLength for e in notes] == [1.0, 0.25]
    assert [e.tie.type for e in notes] == ["start", "stop"]
    assert all(e.duration.type != "complex" for e in content(measures(score.parts[0])[0]))


def test_simultaneous_notes_become_a_chord():
    score = build_score([q(60, 0, 4), q(64, 0, 4), q(67, 0, 4)], [], make_grid(bars=1), "t")
    chords = [e for e in content(measures(score.parts[0])[0]) if isinstance(e, chord.Chord)]
    assert len(chords) == 1
    assert sorted(p.midi for p in chords[0].pitches) == [60, 64, 67]


def test_pickup_is_a_short_first_measure():
    grid = make_grid(3, 4, bars=2, pickup=4)
    score = build_score([q(72, 0, 4), q(74, 4, 4)], [q(48, 4, 12)], grid, "t")
    for part in score.parts:
        ms = measures(part)
        assert len(ms) == grid.bars == 3
        assert ms[0].number == 0 and ms[1].number == 1
        assert sum(e.duration.quarterLength for e in content(ms[0])) == 1.0
        assert ms[0].paddingLeft == 2.0
        for m in ms[1:]:
            assert sum(e.duration.quarterLength for e in content(m)) == 3.0


def test_compound_meter_6_8_bar_is_three_quarters_long():
    grid = make_grid(6, 8, bpb=2, spb=6, bars=2)
    score = build_score([q(72, 0, 3), q(74, 3, 3), q(76, 6, 6)], [], grid, "t")
    assert score.parts[0].recurse().getElementsByClass(meter.TimeSignature)[0].ratioString == "6/8"
    for m in measures(score.parts[0]):
        assert sum(e.duration.quarterLength for e in content(m)) == pytest.approx(3.0)


@pytest.mark.parametrize(
    "num, den, bpb, spb",
    [
        (2, 4, 2, 4),
        (3, 4, 3, 4),
        (4, 4, 4, 4),
        (3, 8, 3, 2),
        (6, 8, 2, 6),
        (9, 8, 3, 6),
        (12, 8, 4, 6),
    ],
)
def test_all_meters_have_representable_durations_and_full_bars(num, den, bpb, spb):
    grid = make_grid(num, den, bpb, spb, bars=3)
    score = build_score([q(72, 1, 7)], [], grid, "t")
    for part in score.parts:
        for m in measures(part):
            assert sum(e.duration.quarterLength for e in content(m)) == pytest.approx(
                grid.steps_per_bar / 4
            )
            assert all(e.duration.type != "complex" for e in content(m))


def test_positions_durations_and_pitches_survive_exactly():
    notes = [
        q(72, 0, 2),
        q(74, 2, 2),
        q(76, 4, 4),
        q(72, 8, 7),  # über Taktstrich
        q(60, 15, 1),
        q(64, 15, 1),
        q(79, 20, 12),
        q(81, 40, 3),
    ]
    score = build_score(notes, [], make_grid(4, 4, bars=3), "t")
    got = sorted(
        (p, start, dur) for pitches, start, dur in rebuild(score.parts[0]) for p in pitches
    )
    assert got == sorted((n.pitch, n.start, n.duration) for n in notes)
