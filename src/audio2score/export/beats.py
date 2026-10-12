import json
import os
from pathlib import Path

import numpy as np

from audio2score.rhythm.base import Beats
from audio2score.rhythm.meter import Grid

TOLERANCE = 1e-6  # Sekunden: so nah muss ein Rasterbeat an einem erkannten Beat liegen


def write_beats_json(grid: Grid, beats: Beats, path: Path, audio_name: str) -> None:
    """Beat-Raster der Partitur: Takt, Zählzeit, Downbeat; `detected` false = fortgesetzt."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    bpb = grid.meter.beats_per_bar
    detected = np.asarray(beats.times)
    entries = []
    for i, t in enumerate(grid.beat_times):
        if i < grid.first_bar_beat:  # Auftakt
            bar, beat = 0, bpb - (grid.first_bar_beat - i) + 1
        else:
            bar, beat = 1 + (i - grid.first_bar_beat) // bpb, (i - grid.first_bar_beat) % bpb + 1
        entries.append(
            {
                "time": round(t, 4),
                "bar": bar,
                "beat": beat,
                "downbeat": beat == 1,
                "detected": bool(np.abs(detected - t).min() < TOLERANCE),
            }
        )
    data = {
        "audio": audio_name,
        "tracker": beats.tracker,
        "tracker_version": beats.tracker_version,
        "time_sig": f"{grid.meter.numerator}/{grid.meter.denominator}",
        "time_sig_source": grid.meter.source,
        "tempo_bpm": round(grid.tempo_bpm, 2),
        "pickup_steps": grid.pickup_steps,
        "bars": grid.bars,
        "irregular_share": round(grid.irregular_share, 4),
        "beats": entries,
    }
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(tmp, path)
