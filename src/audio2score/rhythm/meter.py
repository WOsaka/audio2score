from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass
from statistics import median
from typing import Literal

import numpy as np

from audio2score.model import Note
from audio2score.rhythm.base import Beats, RhythmError

ALLOWED_TIME_SIGS = ["2/4", "3/4", "4/4", "3/8", "6/8", "9/8", "12/8"]
MIN_BEATS = 4
IRREGULAR_WARN = 0.2
DEFAULT_TIME_SIG = (4, 4)


@dataclass(frozen=True)
class Meter:
    numerator: int
    denominator: int  # 4 oder 8
    beats_per_bar: int  # 3/4 → 3; 6/8 → 2 (punktierte Viertel) oder 6 (Achtel)
    steps_per_beat: int  # Sechzehntel pro Beat: 4 (Viertel), 6 (punktierte Viertel), 2 (Achtel)
    source: Literal["detected", "given", "default"]


@dataclass(frozen=True)
class Grid:
    meter: Meter
    beat_times: list[float]  # ab Partituranfang; vor/nach den erkannten Beats fortgesetzt
    first_bar_beat: int  # Index des ersten vollen Taktanfangs in beat_times
    pickup_steps: int  # Länge des Auftakts in Sechzehnteln (0 = kein Auftakt)
    tempo_bpm: float  # Median der Beat-Abstände, auf Viertel umgerechnet
    irregular_share: float  # Anteil der Downbeats, die nicht zur Phase passen
    warnings: tuple[str, ...] = ()

    @property
    def steps_per_bar(self) -> int:
        return self.meter.beats_per_bar * self.meter.steps_per_beat

    @property
    def bars(self) -> int:
        """Takte inklusive Auftakt."""
        full = (len(self.beat_times) - 1 - self.first_bar_beat) // self.meter.beats_per_bar
        return full + (1 if self.pickup_steps else 0)


def parse_time_sig(text: str) -> tuple[int, int]:
    allowed = ", ".join(ALLOWED_TIME_SIGS)
    if text.strip() not in ALLOWED_TIME_SIGS:
        raise ValueError(f"Ungültige Taktart '{text}'. Erlaubt: {allowed}")
    n, d = text.strip().split("/")
    return int(n), int(d)


def beat_position(times: list[float], t: float, steps_per_beat: int) -> int:
    """Sechzehntel-Position von `t` ab `times[0]`; linear zwischen zwei Beats.

    Außerhalb der Beats wird das erste bzw. letzte Intervall fortgesetzt.
    """
    i = min(max(bisect_right(times, t) - 1, 0), len(times) - 2)
    frac = (t - times[i]) / (times[i + 1] - times[i])
    return i * steps_per_beat + round(frac * steps_per_beat)


def _mode(values) -> int:
    """Häufigster Wert, bei Gleichstand der kleinste."""
    counts = Counter(values)
    top = max(counts.values())
    return min(v for v, c in counts.items() if c == top)


def _downbeat_indices(beats: Beats) -> list[int]:
    times = np.asarray(beats.times)
    return sorted({int(np.abs(times - d).argmin()) for d in beats.downbeats})


def detect_meter(beats: Beats, time_sig: tuple[int, int] | None) -> tuple[Meter, list[str]]:
    indices = _downbeat_indices(beats)
    gaps = [b - a for a, b in zip(indices, indices[1:], strict=False)]
    detected = _mode(gaps) if gaps else None
    warnings: list[str] = []

    if time_sig is None:
        if detected in (2, 3, 4):
            return Meter(detected, 4, detected, 4, "detected"), warnings
        if detected is None:
            warnings.append("Keine Downbeats erkannt, 4/4 angenommen (oder --time-sig angeben)")
        else:
            warnings.append(
                f"Erkannte {detected} Beats pro Takt passen zu keiner Taktart "
                "(2/4, 3/4, 4/4), 4/4 angenommen (oder --time-sig angeben)"
            )
        n, d = DEFAULT_TIME_SIG
        return Meter(n, d, n, 4, "default"), warnings

    n, d = time_sig
    if d == 4:
        return Meter(n, 4, n, 4, "given"), warnings
    if detected == n or n == 3:  # Beats sind Achtel
        return Meter(n, 8, n, 2, "given"), warnings
    return Meter(n, 8, n // 3, 6, "given"), warnings  # punktierte Viertel


def _phase(beats: Beats, beats_per_bar: int) -> tuple[int, float]:
    indices = _downbeat_indices(beats)
    if not indices:
        return 0, 0.0
    phase = _mode(i % beats_per_bar for i in indices)
    off = sum(1 for i in indices if i % beats_per_bar != phase)
    return phase, off / len(indices)


def _prepend(times: list[float], count: int, step: float) -> list[float]:
    first = times[0]
    return [first - step * k for k in range(count, 0, -1)] + times


def _extend_to(times: list[float], t: float, step: float) -> None:
    while times[-1] < t - 1e-9:
        times.append(times[-1] + step)


def build_grid(beats: Beats, notes: list[Note], time_sig: tuple[int, int] | None) -> Grid:
    if len(beats.times) < MIN_BEATS:
        raise RhythmError(
            f"Nur {len(beats.times)} Beats erkannt (Stück zu kurz oder frei gespielt); "
            "für eine Partitur braucht es mindestens 4. Eine feste Taktart per --time-sig hilft "
            "nur, wenn Beats gefunden werden."
        )
    if not notes:
        raise RhythmError("Keine Noten vorhanden")

    meter, warnings = detect_meter(beats, time_sig)
    bpb, s = meter.beats_per_bar, meter.steps_per_beat
    bar_steps = bpb * s
    phase, irregular = _phase(beats, bpb)
    if irregular > IRREGULAR_WARN:
        warnings.append(
            f"Uneinheitliche Takte: {irregular:.0%} der erkannten Downbeats passen nicht "
            f"zum {meter.numerator}/{meter.denominator}-Raster (Taktart prüfen, ggf. --time-sig)"
        )

    detected = beats.times
    tempo = 15 * s / median(np.diff(detected))
    front_step = float(median(np.diff(detected[:5])))
    back_step = float(median(np.diff(detected[-5:])))
    t_first = min(n.onset for n in notes)
    t_last = max(n.offset for n in notes)

    # Raster so weit fortsetzen, dass alle Noten abgedeckt sind
    times = list(detected)
    k = 0
    if times[0] > t_first:
        k = int(np.ceil((times[0] - t_first) / front_step - 1e-9))
        times = _prepend(times, k, front_step)
    _extend_to(times, t_last, back_step)
    bar_start = (phase + k) % bpb  # Index des ersten Taktanfangs im erweiterten Raster
    p0 = beat_position(times, t_first, s)
    if p0 < bar_start * s:  # erste Note vor dem ersten Taktanfang: einen Takt davor ergänzen
        times = _prepend(times, bpb, front_step)
        p0 += bpb * s

    # Partituranfang: Takt der ersten Note, bei Note in der zweiten Takthälfte als Auftakt
    rel = p0 - bar_start * s
    bar_begin = bar_start * s + (rel // bar_steps) * bar_steps
    offset = p0 - bar_begin
    if offset * 2 >= bar_steps:
        start = bar_begin + (offset // s) * s
        pickup = bar_begin + bar_steps - start
    else:
        start, pickup = bar_begin, 0
    times = times[start // s :]
    first_bar_beat = pickup // s

    # Ende auf einem Taktstrich, mindestens ein voller Takt
    _extend_to(times, t_last, back_step)
    while (len(times) - 1 - first_bar_beat) % bpb or len(times) - 1 < first_bar_beat + bpb:
        times.append(times[-1] + back_step)

    return Grid(meter, times, first_bar_beat, pickup, float(tempo), irregular, tuple(warnings))
