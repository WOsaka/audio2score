import json
import os
from dataclasses import dataclass
from pathlib import Path

PITCH_MIN, PITCH_MAX = 21, 108


@dataclass(frozen=True)
class Note:
    pitch: int  # MIDI 21–108
    onset: float  # Sekunden
    offset: float  # Sekunden, Tasten-Offset (> onset)
    velocity: int  # 1–127

    def __post_init__(self) -> None:
        if not PITCH_MIN <= self.pitch <= PITCH_MAX:
            raise ValueError(f"Pitch außerhalb {PITCH_MIN}–{PITCH_MAX}: {self.pitch}")
        if not 1 <= self.velocity <= 127:
            raise ValueError(f"Velocity außerhalb 1–127: {self.velocity}")
        if self.onset < 0:
            raise ValueError(f"Onset negativ: {self.onset}")
        if self.offset <= self.onset:
            raise ValueError(f"Offset ({self.offset}) muss nach Onset ({self.onset}) liegen")


@dataclass(frozen=True)
class PedalEvent:
    """Sustain-Pedal."""

    onset: float
    offset: float

    def __post_init__(self) -> None:
        if self.onset < 0 or self.offset <= self.onset:
            raise ValueError(f"Ungültiges Pedal-Event: {self.onset}–{self.offset}")


@dataclass
class NoteList:
    notes: list[Note]  # sortiert nach (onset, pitch)
    pedals: list[PedalEvent]
    duration: float  # Audiolänge in s
    backend: str
    backend_version: str

    def __post_init__(self) -> None:
        self.notes = sorted(self.notes, key=lambda n: (n.onset, n.pitch))

    def to_dict(self) -> dict:
        return {
            "notes": [[n.pitch, n.onset, n.offset, n.velocity] for n in self.notes],
            "pedals": [[p.onset, p.offset] for p in self.pedals],
            "duration": self.duration,
            "backend": self.backend,
            "backend_version": self.backend_version,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "NoteList":
        return cls(
            notes=[Note(int(p), float(on), float(off), int(v)) for p, on, off, v in d["notes"]],
            pedals=[PedalEvent(float(on), float(off)) for on, off in d["pedals"]],
            duration=float(d["duration"]),
            backend=d["backend"],
            backend_version=d["backend_version"],
        )

    def to_json(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(self.to_dict()), encoding="utf-8")
        os.replace(tmp, path)

    @classmethod
    def from_json(cls, path: Path) -> "NoteList":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
