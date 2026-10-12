import pytest

from audio2score.model import Note
from audio2score.rhythm.base import Beats, RhythmError
from audio2score.rhythm.meter import build_grid, parse_time_sig


def make_beats(n_beats=60, dt=0.5, t0=0.0, downbeat_idx=(), times=None):
    times = times or [t0 + i * dt for i in range(n_beats)]
    return Beats(times, [times[i] for i in downbeat_idx], "fake", "1")


def bars_of(bpb, n_bars, offset=0):
    return [offset + i * bpb for i in range(n_bars)]


def note(on, off=None, pitch=60):
    return Note(pitch, on, off if off is not None else on + 0.2, 80)


# --- parse_time_sig ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["2/4", "3/4", "4/4", "3/8", "6/8", "9/8", "12/8"])
def test_parse_allowed(text):
    n, d = text.split("/")
    assert parse_time_sig(text) == (int(n), int(d))


@pytest.mark.parametrize("text", ["5/4", "7/8", "x", "3-4", "", "3/4/4"])
def test_parse_invalid_lists_allowed_values(text):
    with pytest.raises(ValueError, match="12/8"):
        parse_time_sig(text)


# --- Fehlerfälle ------------------------------------------------------------------------------


def test_too_few_beats():
    with pytest.raises(RhythmError, match="Beats"):
        build_grid(make_beats(3), [note(0.0)], None)


def test_no_notes():
    with pytest.raises(RhythmError, match="Noten"):
        build_grid(make_beats(), [], None)


# --- Taktart-Erkennung ------------------------------------------------------------------------


@pytest.mark.parametrize("bpb", [2, 3, 4])
def test_detects_n_over_4_from_downbeat_mode(bpb):
    grid = build_grid(make_beats(downbeat_idx=bars_of(bpb, 12)), [note(0.0)], None)
    m = grid.meter
    assert (m.numerator, m.denominator, m.beats_per_bar, m.steps_per_beat) == (bpb, 4, bpb, 4)
    assert m.source == "detected"
    assert grid.steps_per_bar == 4 * bpb
    assert grid.warnings == ()


def test_unusual_downbeat_mode_falls_back_to_default_with_warning():
    grid = build_grid(make_beats(downbeat_idx=bars_of(5, 10)), [note(0.0)], None)
    assert (grid.meter.numerator, grid.meter.source) == (4, "default")
    assert any("5" in w for w in grid.warnings)


def test_no_downbeats_gives_default_4_4_starting_at_first_beat():
    grid = build_grid(make_beats(), [note(0.0)], None)
    assert (grid.meter.numerator, grid.meter.denominator, grid.meter.source) == (4, 4, "default")
    assert any("Downbeat" in w for w in grid.warnings)
    assert grid.pickup_steps == 0


def test_given_time_sig_overrides_detection():
    beats = make_beats(downbeat_idx=bars_of(4, 12))
    grid = build_grid(beats, [note(0.0)], (3, 4))
    assert (grid.meter.numerator, grid.meter.beats_per_bar, grid.meter.source) == (3, 3, "given")


@pytest.mark.parametrize(
    "given, detected_bpb, expected_bpb, expected_steps",
    [
        ((3, 8), 3, 3, 2),  # Beats sind Achtel (wie bei BWV 856)
        ((3, 8), 1, 3, 2),  # unklar: trotzdem Achtel
        ((6, 8), 2, 2, 6),  # punktierte Viertel
        ((6, 8), 6, 6, 2),  # Achtel
        ((6, 8), 4, 2, 6),  # unklar: punktierte Viertel
        ((9, 8), 3, 3, 6),
        ((12, 8), 4, 4, 6),
    ],
)
def test_n_over_8_reads_beat_level_from_detected_mode(
    given, detected_bpb, expected_bpb, expected_steps
):
    beats = make_beats(downbeat_idx=bars_of(detected_bpb, 10))
    m = build_grid(beats, [note(0.0)], given).meter
    assert (m.beats_per_bar, m.steps_per_beat) == (expected_bpb, expected_steps)
    assert (m.numerator, m.denominator) == given
    # ein Takt n/8 hat immer n/2 Sechzehntel
    assert m.beats_per_bar * m.steps_per_beat == given[0] * 2


def test_tempo_is_median_beat_distance_in_quarters():
    four = build_grid(make_beats(dt=0.5, downbeat_idx=bars_of(4, 12)), [note(0.0)], None)
    assert four.tempo_bpm == pytest.approx(120)
    dotted = build_grid(make_beats(dt=0.5, downbeat_idx=bars_of(2, 12)), [note(0.0)], (6, 8))
    assert dotted.tempo_bpm == pytest.approx(180)  # punktierte Viertel = 120 → Viertel = 180
    eighths = build_grid(make_beats(dt=0.25, downbeat_idx=bars_of(3, 12)), [note(0.0)], (3, 8))
    assert eighths.tempo_bpm == pytest.approx(120)


# --- Phase ------------------------------------------------------------------------------------


def test_outlier_downbeat_does_not_shift_bars():
    idx = [*bars_of(3, 6), 20, *bars_of(3, 8, offset=21)]  # 20 liegt neben dem Raster
    grid = build_grid(make_beats(downbeat_idx=idx), [note(0.0)], None)
    assert grid.first_bar_beat == 0
    assert grid.irregular_share == pytest.approx(1 / 15)
    assert not any("uneinheitlich" in w.lower() for w in grid.warnings)


def test_many_irregular_downbeats_warn():
    idx = [0, 3, 6, 10, 13, 16, 19, 23]  # 5 von 8 nicht auf Phase 0
    grid = build_grid(make_beats(downbeat_idx=idx), [note(0.0)], (3, 4))
    assert grid.irregular_share > 0.2
    assert any("uneinheitlich" in w.lower() for w in grid.warnings)


def test_phase_shifts_bar_start_and_drops_empty_leading_bars():
    # Downbeats auf Beat 1, 4, 7 … (Phase 1): Takt beginnt am zweiten Beat.
    # Erste Note am Beat 7 (Taktanfang) → Raster beginnt dort, leere Takte davor entfallen.
    beats = make_beats(downbeat_idx=bars_of(3, 15, offset=1))
    grid = build_grid(beats, [note(7 * 0.5)], None)
    assert grid.pickup_steps == 0
    assert grid.first_bar_beat == 0
    assert grid.beat_times[0] == pytest.approx(7 * 0.5)


# --- Auftakt ----------------------------------------------------------------------------------


def test_first_note_in_second_half_of_bar_makes_a_pickup():
    beats = make_beats(downbeat_idx=bars_of(3, 15))  # 3/4, Takt 0 = Beats 0–2
    grid = build_grid(beats, [note(2 * 0.5)], None)  # Note auf Beat 3 des ersten Takts
    assert grid.pickup_steps == 4
    assert grid.first_bar_beat == 1
    assert grid.beat_times[0] == pytest.approx(2 * 0.5)


def test_pickup_starts_at_the_beat_of_the_first_note():
    beats = make_beats(downbeat_idx=bars_of(4, 12))  # 4/4: 16 Sechzehntel
    # zweiter Takt (Beats 4–7), erste Note eine Sechzehntel nach Beat 7 (Index 6)
    grid = build_grid(beats, [note(6 * 0.5 + 0.125)], None)
    assert grid.pickup_steps == 16 - 8  # Beat 7 steht 8 Sechzehntel nach dem Taktanfang
    assert grid.beat_times[0] == pytest.approx(6 * 0.5)
    assert grid.first_bar_beat == 2


def test_first_note_in_first_half_gives_full_bar_with_rest_before():
    beats = make_beats(downbeat_idx=bars_of(4, 12))
    grid = build_grid(beats, [note(1 * 0.5)], None)  # zweiter Beat des ersten Takts
    assert grid.pickup_steps == 0
    assert grid.beat_times[0] == pytest.approx(0.0)


def test_leading_bars_without_notes_are_dropped():
    beats = make_beats(downbeat_idx=bars_of(3, 15))
    grid = build_grid(beats, [note(9 * 0.5)], None)  # Takt 3
    assert grid.beat_times[0] == pytest.approx(9 * 0.5)
    assert grid.pickup_steps == 0


# --- Raster fortsetzen ------------------------------------------------------------------------


def test_grid_is_continued_before_the_first_beat():
    beats = make_beats(8, dt=0.5, t0=1.0, downbeat_idx=[0, 4])
    grid = build_grid(beats, [note(0.5)], None)
    assert grid.beat_times[0] <= 0.5 + 1e-9
    steps = [b - a for a, b in zip(grid.beat_times, grid.beat_times[1:], strict=False)]
    assert steps == pytest.approx([0.5] * len(steps))


def test_grid_is_continued_after_the_last_beat_to_a_bar_line():
    beats = make_beats(8, dt=0.5, downbeat_idx=[0, 4])  # Beats bis 3.5 s
    grid = build_grid(beats, [note(0.0, 7.2)], None)
    assert grid.beat_times[-1] >= 7.2
    assert (len(grid.beat_times) - 1 - grid.first_bar_beat) % grid.meter.beats_per_bar == 0
    assert grid.bars == (len(grid.beat_times) - 1) // 4


def test_continuation_uses_local_tempo_at_the_ends():
    times = [0.0, 1.0, 1.9, 2.7, 3.4, 4.0, 4.5, 4.9]  # Accelerando
    grid = build_grid(make_beats(times=times, downbeat_idx=[0, 4]), [note(0.0, 6.0)], None)
    # Median der letzten vier Abstände
    tail = [b - a for a, b in zip(grid.beat_times[7:], grid.beat_times[8:], strict=False)]
    assert tail and tail == pytest.approx([0.55] * len(tail), abs=1e-6)


def test_note_before_the_first_bar_start_gets_an_earlier_bar():
    # Phase 2: erster Taktanfang bei Beat 2; Note bei Beat 0 liegt davor
    beats = make_beats(downbeat_idx=bars_of(4, 12, offset=2))
    grid = build_grid(beats, [note(0.0)], None)
    assert grid.beat_times[0] <= 0.0 + 1e-9
    assert grid.bars >= 1
