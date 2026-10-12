import bisect
import statistics
from dataclasses import dataclass

from audio2score.model import NoteList

_WINDOW = 1.0  # s, Fenster für den Median der Velocity (±)


@dataclass(frozen=True)
class CleanupConfig:
    min_duration: float = 0.03  # s
    min_velocity: int = 8
    relative_velocity: float = 0.2  # Anteil am Median der Velocity im ±1-s-Fenster
    ghost_onset_tolerance: float = 0.03  # s
    ghost_velocity_ratio: float = 0.5


def cleanup(nl: NoteList, cfg: CleanupConfig | None = None) -> NoteList:
    """Entfernt Artefakte; Pedale und Metadaten bleiben unverändert, die Eingabe auch."""
    cfg = cfg or CleanupConfig()
    notes = [
        n
        for n in nl.notes
        if n.offset - n.onset >= cfg.min_duration and n.velocity >= cfg.min_velocity
    ]

    onsets = [n.onset for n in notes]  # nl.notes ist nach Onset sortiert, die Filterung erhält das
    kept = []
    for n in notes:
        lo = bisect.bisect_left(onsets, n.onset - _WINDOW)
        hi = bisect.bisect_right(onsets, n.onset + _WINDOW)
        median = statistics.median(m.velocity for m in notes[lo:hi])
        if n.velocity >= cfg.relative_velocity * median:
            kept.append(n)

    kept_onsets = [n.onset for n in kept]

    def is_ghost(n) -> bool:
        lo = bisect.bisect_left(kept_onsets, n.onset - cfg.ghost_onset_tolerance)
        hi = bisect.bisect_right(kept_onsets, n.onset + cfg.ghost_onset_tolerance)
        return any(
            m.pitch == n.pitch - 12
            and m.velocity > n.velocity
            and n.velocity < cfg.ghost_velocity_ratio * m.velocity
            for m in kept[lo:hi]
        )

    result = [n for n in kept if not is_ghost(n)]  # gegen die Liste vor dem Geister-Schritt prüfen
    return NoteList(result, list(nl.pedals), nl.duration, nl.backend, nl.backend_version)
