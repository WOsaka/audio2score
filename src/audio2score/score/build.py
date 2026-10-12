from itertools import groupby

from music21 import chord, clef, layout, metadata, meter, note, stream, tempo, tie

from audio2score.rhythm.meter import Grid
from audio2score.rhythm.quantize import QNote

QUARTERS_PER_STEP = 0.25  # eine Sechzehntel
# Darstellbare Dauern in Sechzehnteln: Ganze, punktierte Halbe, Halbe, punktierte Viertel, ...
DURATIONS = (16, 12, 8, 6, 4, 3, 2, 1)


def _pieces(pos: int, length: int, steps_per_beat: int) -> list[int]:
    """Zerlegt `length` ab Taktposition `pos` in darstellbare Dauern.

    Ein Stück beginnt mitten in einem Beat nur bis zum nächsten Beat; auf einem Beat darf es
    entweder innerhalb des Beats bleiben oder ganze Beats umfassen.
    """
    s = steps_per_beat
    out = []
    while length > 0:
        on_beat = pos % s == 0
        room = s - pos % s
        d = next(
            d
            for d in DURATIONS
            if d <= length and ((d <= s or d % s == 0) if on_beat else d <= room)
        )
        out.append(d)
        pos += d
        length -= d
    return out


def _chords(notes: list[QNote]) -> list[tuple[int, int, list[int]]]:
    """(Start, Dauer, Tonhöhen) je Onset; die Dauer ist die längste der Gruppe."""
    ordered = sorted(notes, key=lambda n: (n.start, n.pitch))
    result = []
    for start, group in groupby(ordered, key=lambda n: n.start):
        group = list(group)
        result.append((start, max(n.duration for n in group), sorted({n.pitch for n in group})))
    return result


def _measure_bounds(grid: Grid) -> list[tuple[int, int, int]]:
    """(Start, Ende, Taktposition des Starts) je Takt in Sechzehnteln, Auftakt zuerst."""
    bar = grid.steps_per_bar
    bounds = []
    pos = 0
    if grid.pickup_steps:
        bounds.append((0, grid.pickup_steps, bar - grid.pickup_steps))
        pos = grid.pickup_steps
    full = (len(grid.beat_times) - 1 - grid.first_bar_beat) // grid.meter.beats_per_bar
    for _ in range(full):
        bounds.append((pos, pos + bar, 0))
        pos += bar
    return bounds


def _element(pitches: list[int], steps: int):
    ql = steps * QUARTERS_PER_STEP
    if len(pitches) == 1:
        return note.Note(midi=pitches[0], quarterLength=ql)
    return chord.Chord(pitches, quarterLength=ql)


def _set_tie(element, kind: str) -> None:
    for n in element.notes if isinstance(element, chord.Chord) else [element]:
        n.tie = tie.Tie(kind)


def _add_rests(
    measure: stream.Measure, frm: int, to: int, m_start: int, m_pos: int, s: int
) -> None:
    at = frm
    for d in _pieces(m_pos + frm - m_start, to - frm, s) if to > frm else []:
        measure.insert((at - m_start) * QUARTERS_PER_STEP, note.Rest(quarterLength=d * 0.25))
        at += d


def _build_part(notes: list[QNote], grid: Grid, clef_obj, with_tempo: bool) -> stream.PartStaff:
    s = grid.meter.steps_per_beat
    bounds = _measure_bounds(grid)
    part = stream.PartStaff()

    # Segmente je Takt: (Start, Ende, Tonhöhen, Nummer des Akkords)
    per_measure: list[list[tuple[int, int, list[int], int]]] = [[] for _ in bounds]
    cursor = 0
    for number, (start, duration, pitches) in enumerate(_chords(notes)):
        start = max(start, cursor)  # keine Überlappung innerhalb einer Hand
        end = start + duration
        for index, (m_start, m_end, _) in enumerate(bounds):
            seg_start, seg_end = max(start, m_start), min(end, m_end)
            if seg_start < seg_end:
                per_measure[index].append((seg_start, seg_end, pitches, number))
        cursor = end

    pieces_of: dict[int, list] = {}
    for index, (m_start, m_end, m_pos) in enumerate(bounds):
        measure = stream.Measure(number=index if grid.pickup_steps else index + 1)
        if index == 0:
            measure.append(clef_obj)
            measure.append(meter.TimeSignature(f"{grid.meter.numerator}/{grid.meter.denominator}"))
            if with_tempo:
                measure.append(tempo.MetronomeMark(number=round(grid.tempo_bpm)))
        if m_pos:
            measure.paddingLeft = m_pos * QUARTERS_PER_STEP

        cursor = m_start
        for seg_start, seg_end, pitches, number in per_measure[index]:
            _add_rests(measure, cursor, seg_start, m_start, m_pos, s)
            at = seg_start
            for d in _pieces(m_pos + seg_start - m_start, seg_end - seg_start, s):
                el = _element(pitches, d)
                measure.insert((at - m_start) * QUARTERS_PER_STEP, el)
                pieces_of.setdefault(number, []).append(el)
                at += d
            cursor = seg_end
        _add_rests(measure, cursor, m_end, m_start, m_pos, s)
        part.append(measure)

    for pieces in pieces_of.values():  # Haltebögen: innerhalb des Takts und über Taktstriche
        for i, el in enumerate(pieces):
            if i < len(pieces) - 1:
                _set_tie(el, "start" if i == 0 else "continue")
            elif i > 0:
                _set_tie(el, "stop")
    part.makeBeams(inPlace=True)
    return part


def build_score(right: list[QNote], left: list[QNote], grid: Grid, title: str) -> stream.Score:
    score = stream.Score()
    score.metadata = metadata.Metadata(title=title)
    upper = _build_part(right, grid, clef.TrebleClef(), True)
    lower = _build_part(left, grid, clef.BassClef(), False)
    score.insert(0, upper)
    score.insert(0, lower)
    score.insert(
        0, layout.StaffGroup([upper, lower], name="Piano", symbol="brace", barTogether=True)
    )
    return score
