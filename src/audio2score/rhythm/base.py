from dataclasses import dataclass
from typing import Protocol

import numpy as np


class RhythmError(Exception):
    """Keine Noten oder zu wenige Beats für eine Partitur."""


@dataclass(frozen=True)
class Beats:
    times: list[float]  # Sekunden, aufsteigend
    downbeats: list[float]  # Teilmenge von times (auf den nächsten Beat eingerastet)
    tracker: str
    tracker_version: str  # fließt in den Cache-Schlüssel ein

    def to_dict(self) -> dict:
        return {
            "times": self.times,
            "downbeats": self.downbeats,
            "tracker": self.tracker,
            "tracker_version": self.tracker_version,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Beats":
        return cls(
            times=[float(t) for t in d["times"]],
            downbeats=[float(t) for t in d["downbeats"]],
            tracker=d["tracker"],
            tracker_version=d["tracker_version"],
        )


class BeatTracker(Protocol):
    name: str
    version: str  # fließt in den Cache-Schlüssel ein

    def track(self, audio: np.ndarray, sample_rate: int) -> Beats: ...
