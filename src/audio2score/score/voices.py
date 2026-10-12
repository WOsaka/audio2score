from itertools import groupby

from audio2score.rhythm.quantize import QNote


def single_voice(notes: list[QNote]) -> list[QNote]:
    """Eine Stimme pro Hand: Akkorde bilden, gleiche Töne zusammenlegen, Dauern kappen."""
    ordered = sorted(notes, key=lambda n: (n.start, n.pitch))
    groups = [(start, list(g)) for start, g in groupby(ordered, key=lambda n: n.start)]
    result: list[QNote] = []
    for i, (start, group) in enumerate(groups):
        merged: dict[int, QNote] = {}
        for note in group:
            old = merged.get(note.pitch)
            if old is None:
                merged[note.pitch] = note
            else:
                velocity = max(old.velocity, note.velocity)
                merged[note.pitch] = QNote(
                    note.pitch, start, max(old.duration, note.duration), velocity
                )
        duration = max(n.duration for n in merged.values())
        if i + 1 < len(groups):
            duration = min(duration, groups[i + 1][0] - start)
        result.extend(QNote(n.pitch, start, duration, n.velocity) for n in merged.values())
    return result
