from dataclasses import dataclass

from audio2score.model import Note
from audio2score.rhythm.meter import Grid, beat_position


@dataclass(frozen=True)
class QNote:
    pitch: int
    start: int  # Sechzehntel ab Partituranfang (Auftakt-Anfang = 0)
    duration: int  # Sechzehntel, >= 1
    velocity: int


def quantize(notes: list[Note], grid: Grid) -> list[QNote]:
    """Sekunden → Sechzehntel-Positionen, linear zwischen den Beats des Rasters."""
    s = grid.meter.steps_per_beat
    result = []
    for note in notes:
        start = max(0, beat_position(grid.beat_times, note.onset, s))
        end = beat_position(grid.beat_times, note.offset, s)
        result.append(QNote(note.pitch, start, max(1, end - start), note.velocity))
    return result
