import json

import mido
import pretty_midi
import pytest
from music21 import converter, meter, stream

from audio2score.export.beats import write_beats_json
from audio2score.export.musicxml import write_musicxml
from audio2score.export.quantized_midi import write_quantized_midi
from audio2score.model import Note
from audio2score.rhythm.base import Beats
from audio2score.rhythm.meter import Grid, Meter, build_grid
from audio2score.rhythm.quantize import QNote, quantize
from audio2score.score.build import build_score
from audio2score.score.hands import split_hands
from audio2score.score.voices import single_voice


def piece(time_sig=(3, 4), first_note_idx=0):
    """Kleine Partitur aus synthetischen Beats; gibt (Beats, Grid, rechts, links) zurück."""
    times = [i * 0.5 for i in range(14)]
    beats = Beats(times, times[:: time_sig[0]], "fake", "1")
    base = first_note_idx * 0.5  # Zeit des ersten Beats mit Noten
    notes = [Note(72 + i % 5, base + i * 0.25, base + i * 0.25 + 0.2, 70) for i in range(24)]
    notes.append(Note(48, base, base + 1.4, 60))
    grid = build_grid(beats, notes, time_sig)
    right, left = split_hands(quantize(notes, grid))
    return beats, grid, single_voice(right), single_voice(left)


# --- MusicXML ---------------------------------------------------------------------------------


def test_musicxml_roundtrip_with_music21(tmp_path):
    _, grid, right, left = piece()
    score = build_score(right, left, grid, "Probe")
    path = tmp_path / "out" / "probe.musicxml"
    write_musicxml(score, path)
    back = converter.parse(path)
    assert len(back.parts) == 2  # zwei Systeme
    for part in back.parts:
        assert len(part.getElementsByClass(stream.Measure)) == grid.bars
        assert part.recurse().getElementsByClass(meter.TimeSignature)[0].ratioString == "3/4"
    right_pitches = {n.pitch.midi for n in back.parts[0].recurse().notes if hasattr(n, "pitch")}
    assert {72, 73, 74, 75, 76} <= right_pitches
    assert back.metadata.movementName == "Probe"  # music21 liest den Titel als Satzname
    assert "Music21" not in path.read_text(encoding="utf-8")  # kein Fantasie-Komponist


def test_musicxml_marks_the_pickup_measure_as_implicit(tmp_path):
    _, grid, right, left = piece(first_note_idx=2)  # Note auf dem dritten Beat → Auftakt
    assert grid.pickup_steps > 0
    path = tmp_path / "p.musicxml"
    write_musicxml(build_score(right, left, grid, "t"), path)
    xml = path.read_text(encoding="utf-8")
    assert 'implicit="yes" number="0"' in xml
    assert 'implicit="no" number="1"' in xml


# --- Quantisiertes MIDI -----------------------------------------------------------------------


def midi_grid(times, num=4, den=4, bpb=4, spb=4, pickup=0):
    return Grid(Meter(num, den, bpb, spb, "given"), times, pickup // spb, pickup, 120.0, 0.0)


def read_notes(path):
    midi = pretty_midi.PrettyMIDI(str(path))  # leere Spuren erscheinen dort nicht als Instrument
    tracks = [sorted(inst.notes, key=lambda n: n.start) for inst in midi.instruments]
    return midi, tracks + [[]] * (2 - len(tracks))


def test_midi_notes_land_on_beat_times_through_the_tempo_map(tmp_path):
    # beschleunigendes Tempo; Beats beginnen erst bei 1,0 s (Vorlauf nötig)
    times = [1.0, 1.5, 1.9, 2.2, 2.4, 2.55, 2.67, 2.77, 2.86]
    grid = midi_grid(times)
    right = [QNote(72, 0, 4, 80), QNote(74, 4, 4, 80), QNote(76, 8, 2, 90), QNote(77, 14, 2, 90)]
    left = [QNote(48, 0, 16, 60)]
    path = tmp_path / "q.mid"
    write_quantized_midi(right, left, grid, path)
    midi, (r, left_notes) = read_notes(path)
    assert [n.pitch for n in r] == [72, 74, 76, 77]
    assert r[0].start == pytest.approx(1.0, abs=0.005)
    assert r[1].start == pytest.approx(1.5, abs=0.005)
    assert r[2].start == pytest.approx(1.9, abs=0.005)
    assert r[2].end == pytest.approx(2.05, abs=0.005)  # halbe Zählzeit: Mitte zwischen 1,9 und 2,2
    assert r[3].start == pytest.approx(2.3, abs=0.005)  # halbe Zählzeit zwischen 2,2 und 2,4
    assert left_notes[0].start == pytest.approx(1.0, abs=0.005)
    assert [n.velocity for n in r] == [80, 80, 90, 90]


def test_midi_contains_time_signature_and_one_track_per_hand(tmp_path):
    grid = midi_grid([0.5 + i * 0.4 for i in range(12)], 3, 4, 3, 4)
    path = tmp_path / "q.mid"
    write_quantized_midi([QNote(72, 0, 4, 80)], [], grid, path)
    midi = pretty_midi.PrettyMIDI(str(path))
    assert [(t.numerator, t.denominator) for t in midi.time_signature_changes] == [(3, 4)]
    raw = mido.MidiFile(str(path))
    assert raw.type == 1 and raw.ticks_per_beat == 480
    assert [t.name for t in raw.tracks] == ["Tempo", "Rechte Hand", "Linke Hand"]


def test_midi_first_bar_lines_match_when_the_score_has_a_pickup(tmp_path):
    # 3/4, Auftakt von einer Viertel; erste volle Takt beginnt bei Beat 1 → 1,4 s
    times = [1.0 + i * 0.4 for i in range(14)]
    grid = midi_grid(times, 3, 4, 3, 4, pickup=4)
    write_quantized_midi([QNote(72, 0, 4, 80), QNote(74, 4, 12, 80)], [], grid, tmp_path / "p.mid")
    midi, (r, _) = read_notes(tmp_path / "p.mid")
    assert r[0].start == pytest.approx(1.0, abs=0.005)
    assert r[1].start == pytest.approx(1.4, abs=0.005)
    beats = midi.get_beats()
    bar_lines = midi.get_downbeats()
    assert any(abs(b - 1.4) < 0.01 for b in bar_lines)
    assert len(beats) > 0


def test_midi_survives_a_very_long_lead_in(tmp_path):
    grid = midi_grid([100.0 + i * 0.5 for i in range(9)])
    write_quantized_midi([QNote(72, 0, 4, 80)], [], grid, tmp_path / "l.mid")
    _, (r, _) = read_notes(tmp_path / "l.mid")
    assert r[0].start == pytest.approx(100.0, abs=0.01)


def test_midi_with_grid_starting_before_zero_stays_in_sync(tmp_path):
    # Beat-Raster wurde vor 0 s fortgesetzt (Note vor dem ersten erkannten Beat)
    times = [-0.3 + i * 0.5 for i in range(9)]
    grid = midi_grid(times)
    right = [QNote(72, 4, 4, 80), QNote(74, 8, 4, 80)]  # Beat 1 (0,2 s), Beat 2 (0,7 s)
    write_quantized_midi(right, [], grid, tmp_path / "n.mid")
    _, (r, _) = read_notes(tmp_path / "n.mid")
    assert r[0].start == pytest.approx(0.2, abs=0.01)
    assert r[1].start == pytest.approx(0.7, abs=0.01)


def test_midi_repeated_pitch_does_not_overlap(tmp_path):
    grid = midi_grid([0.5 + i * 0.5 for i in range(9)])
    right = [QNote(72, 0, 4, 80), QNote(72, 4, 4, 80)]
    write_quantized_midi(right, [], grid, tmp_path / "r.mid")
    _, (r, _) = read_notes(tmp_path / "r.mid")
    assert len(r) == 2 and r[0].end <= r[1].start + 1e-6


# --- Beat-Datei -------------------------------------------------------------------------------


def test_beats_json_has_bars_beats_and_detected_flags(tmp_path):
    beats, grid, _, _ = piece(first_note_idx=2)
    path = tmp_path / "b" / "x.beats.json"
    write_beats_json(grid, beats, path, "aufnahme.mp3")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["audio"] == "aufnahme.mp3"
    assert (data["tracker"], data["tracker_version"]) == ("fake", "1")
    assert (data["time_sig"], data["time_sig_source"]) == ("3/4", "given")
    assert data["tempo_bpm"] == pytest.approx(120.0)
    assert data["pickup_steps"] == grid.pickup_steps == 4
    assert data["bars"] == grid.bars
    first = data["beats"][0]
    assert (first["bar"], first["beat"], first["downbeat"], first["detected"]) == (
        0,
        3,
        False,
        True,
    )
    second = data["beats"][1]
    assert (second["bar"], second["beat"], second["downbeat"]) == (1, 1, True)
    assert len(data["beats"]) == len(grid.beat_times)
    assert first["time"] == pytest.approx(grid.beat_times[0])


def test_beats_json_marks_continued_beats_as_not_detected(tmp_path):
    beats, grid, _, _ = piece()
    path = tmp_path / "x.json"
    write_beats_json(grid, beats, path, "a.mp3")
    flags = [b["detected"] for b in json.loads(path.read_text(encoding="utf-8"))["beats"]]
    assert flags[0] is True
    assert False in flags  # Raster ist über das letzte erkannte Beat hinaus fortgesetzt
