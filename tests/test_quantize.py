import pytest

from audio2score.model import Note
from audio2score.rhythm.base import Beats
from audio2score.rhythm.meter import build_grid
from audio2score.rhythm.quantize import QNote, quantize


def grid_for(notes, dt=0.5, n_beats=40, times=None, time_sig=(4, 4)):
    times = times or [i * dt for i in range(n_beats)]
    beats = Beats(times, times[::4], "fake", "1")
    return build_grid(beats, notes, time_sig)


def n(on, off, pitch=60, vel=80):
    return Note(pitch, on, off, vel)


def test_notes_exactly_on_sixteenths_stay_exact():
    notes = [n(0.0, 0.125), n(0.125, 0.5), n(0.5, 1.5, 64), n(2.0, 2.375, 67, 99)]
    q = quantize(notes, grid_for(notes))
    assert q == [
        QNote(60, 0, 1, 80),
        QNote(60, 1, 3, 80),
        QNote(64, 4, 8, 80),
        QNote(67, 16, 3, 99),
    ]


def test_deviation_of_40_ms_rounds_to_nearest_sixteenth():
    # Sechzehntel = 125 ms; ±40 ms liegt unter der halben Rasterbreite (62,5 ms)
    notes = [n(0.0, 0.5), n(0.5 + 0.04, 1.0 - 0.04), n(1.0 - 0.04, 1.5 + 0.04), n(1.5, 2.0)]
    q = quantize(notes, grid_for(notes))
    assert [(x.start, x.duration) for x in q] == [(0, 4), (4, 4), (8, 4), (12, 4)]


def test_rounding_is_to_the_nearest_not_down():
    notes = [n(0.0, 0.5), n(0.5 + 0.07, 1.0)]  # 70 ms nach dem Beat → 0,56 Sechzehntel → 5
    q = quantize(notes, grid_for(notes))
    assert q[1].start == 5


def test_tempo_change_between_beats_follows_the_beats():
    # zweites Beat-Intervall doppelt so lang → Note in der Mitte liegt bei einer halben Zählzeit
    times = [0.0, 0.5, 1.5, 2.5, 3.0, 3.5, 4.0, 4.5]
    notes = [n(0.0, 0.5), n(1.0, 1.5), n(2.0, 2.5)]
    q = quantize(notes, grid_for(notes, times=times))
    assert [x.start for x in q] == [0, 6, 10]  # 0.5 s Beat, dann 1 s Beat: 1.0 s = Beat 1.5


def test_minimum_duration_is_one_sixteenth():
    notes = [n(0.0, 0.01), n(0.5, 1.0)]
    q = quantize(notes, grid_for(notes))
    assert q[0] == QNote(60, 0, 1, 80)


def test_notes_before_first_and_after_last_detected_beat_get_positions():
    times = [1.0 + i * 0.5 for i in range(8)]  # 1.0 … 4.5
    notes = [n(0.5, 1.0), n(5.0, 6.0)]
    g = grid_for(notes, times=times)
    q = quantize(notes, g)
    assert q[1].start - q[0].start == 4 * 9  # 4,5 s = 9 Beats = 36 Sechzehntel
    assert q[1].duration == 8
    assert q[0].start >= 0


def test_pickup_note_sits_at_the_end_of_the_first_bar():
    # 3/4, erste Note auf dem dritten Beat → Auftakt von einer Viertel
    times = [i * 0.5 for i in range(30)]
    beats = Beats(times, times[::3], "fake", "1")
    notes = [n(1.0, 1.5), n(1.5, 2.0)]
    g = build_grid(beats, notes, (3, 4))
    q = quantize(notes, g)
    assert g.pickup_steps == 4
    assert [x.start for x in q] == [0, g.pickup_steps]
    assert q[1].start == g.first_bar_beat * g.meter.steps_per_beat


def test_compound_meter_uses_six_sixteenths_per_beat():
    times = [i * 0.5 for i in range(30)]
    beats = Beats(times, times[::2], "fake", "1")
    notes = [n(0.0, 0.25), n(0.25, 0.5), n(0.5, 1.0)]
    g = build_grid(beats, notes, (6, 8))
    q = quantize(notes, g)
    assert [(x.start, x.duration) for x in q] == [(0, 3), (3, 3), (6, 6)]


def test_empty_input():
    notes = [n(0.0, 0.5)]
    assert quantize([], grid_for(notes)) == []


def test_pitch_and_velocity_are_kept():
    notes = [n(0.0, 0.5, pitch=72, vel=33)]
    (q,) = quantize(notes, grid_for(notes))
    assert (q.pitch, q.velocity) == (72, 33)


@pytest.mark.parametrize("dt", [0.3, 0.5, 0.9])
def test_all_quantized_notes_have_nonnegative_start_and_positive_duration(dt):
    notes = [n(0.07 * i, 0.07 * i + 0.05) for i in range(40)]
    for q in quantize(notes, grid_for(notes, dt=dt, n_beats=60)):
        assert q.start >= 0 and q.duration >= 1
