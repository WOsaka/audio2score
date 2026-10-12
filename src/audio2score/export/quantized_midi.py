from pathlib import Path

import mido

from audio2score.rhythm.meter import Grid
from audio2score.rhythm.quantize import QNote

TICKS_PER_QUARTER = 480
TICKS_PER_STEP = TICKS_PER_QUARTER // 4  # eine Sechzehntel
MAX_TEMPO = 0xFFFFFF  # µs pro Viertel, Grenze der MIDI-Tempo-Meldung


def _lead_in_steps(grid: Grid, first_beat_time: float) -> int:
    """Vorlauf in Sechzehnteln: ein Takt (bei Auftakt plus der fehlende Taktteil).

    Das MIDI startet bei Audio-Zeit 0, die Partitur erst am ersten Beat; der Vorlauf
    überbrückt die Zeit dazwischen und hält die Taktstriche auf Taktgrenzen.
    """
    if first_beat_time <= 0:
        return 0
    bar = grid.steps_per_bar
    lead = 2 * bar - grid.pickup_steps if grid.pickup_steps else bar
    while first_beat_time * 1e6 / (lead / 4) > MAX_TEMPO:  # sehr langer Vorlauf
        lead += bar
    return lead


def _track(name: str, notes: list[QNote], offset: int) -> mido.MidiTrack:
    events = []
    for n in notes:
        start = offset + n.start * TICKS_PER_STEP
        events.append(
            (start + n.duration * TICKS_PER_STEP, 0, mido.Message("note_off", note=n.pitch))
        )
        events.append((start, 1, mido.Message("note_on", note=n.pitch, velocity=n.velocity)))
    track = mido.MidiTrack([mido.MetaMessage("track_name", name=name)])
    track.append(mido.Message("program_change", program=0))
    now = 0
    for tick, _, msg in sorted(events, key=lambda e: (e[0], e[1])):  # Ende vor Anfang
        track.append(msg.copy(time=tick - now))
        now = tick
    return track


def write_quantized_midi(right: list[QNote], left: list[QNote], grid: Grid, path: Path) -> None:
    """Typ-1-MIDI: Tempo-Spur (ein Tempo pro Beat) + rechte + linke Hand.

    Die Tempo-Map folgt den Beats der Aufnahme, daher läuft das MIDI synchron zum Audio.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    s = grid.meter.steps_per_beat
    times = grid.beat_times
    lead = _lead_in_steps(grid, times[0])
    offset = lead * TICKS_PER_STEP

    tempos: list[tuple[int, int]] = []
    if lead:
        tempos.append((0, round(times[0] * 1e6 / (lead / 4))))
    for k in range(len(times) - 1):
        micros = round((times[k + 1] - times[k]) * 1e6 / (s / 4))
        tempos.append((offset + k * s * TICKS_PER_STEP, min(max(micros, 1), MAX_TEMPO)))

    tempo_track = mido.MidiTrack(
        [
            mido.MetaMessage("track_name", name="Tempo"),
            mido.MetaMessage(
                "time_signature",
                numerator=grid.meter.numerator,
                denominator=grid.meter.denominator,
            ),
        ]
    )
    now = 0
    for tick, micros in tempos:
        tempo_track.append(mido.MetaMessage("set_tempo", tempo=micros, time=tick - now))
        now = tick

    midi = mido.MidiFile(type=1, ticks_per_beat=TICKS_PER_QUARTER)
    midi.tracks.extend(
        [tempo_track, _track("Rechte Hand", right, offset), _track("Linke Hand", left, offset)]
    )
    midi.save(str(path))
