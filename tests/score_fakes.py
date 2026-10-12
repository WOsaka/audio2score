"""Fake-Backend und Fake-Tracker für die Score-Tests; zählen ihre Aufrufe."""

from audio2score import rhythm
from audio2score import transcribe as transcribe_pkg
from audio2score.model import Note, NoteList
from audio2score.rhythm.base import Beats, RhythmError


class FakeBackend:
    name = "fake"
    version = "1"
    calls = 0
    notes: list[Note] = []

    def transcribe(self, audio, sample_rate):
        FakeBackend.calls += 1
        return NoteList(list(FakeBackend.notes), [], 4.0, "fake", "1")


class FakeTracker:
    name = "fake-tracker"
    version = "1"
    calls = 0
    n_beats = 20
    downbeat_every = 4
    fail_for: set[int] = set()  # Nummern der Aufrufe, die scheitern

    def track(self, audio, sample_rate):
        FakeTracker.calls += 1
        if FakeTracker.calls in FakeTracker.fail_for:
            raise RhythmError("Beat-Fehler")
        times = [i * 0.5 for i in range(FakeTracker.n_beats)]
        return Beats(times, times[:: FakeTracker.downbeat_every], self.name, self.version)


def default_notes() -> list[Note]:
    right = [Note(72 + i % 4, i * 0.5, i * 0.5 + 0.4, 80) for i in range(8)]
    return [*right, Note(48, 0.0, 1.9, 60)]


def install(monkeypatch) -> None:
    FakeBackend.calls = 0
    FakeBackend.notes = default_notes()
    FakeTracker.calls = 0
    FakeTracker.n_beats = 20
    FakeTracker.downbeat_every = 4
    FakeTracker.fail_for = set()
    monkeypatch.setitem(transcribe_pkg._REGISTRY, "fake", lambda **options: FakeBackend())
    monkeypatch.setitem(rhythm._REGISTRY, "fake-tracker", lambda **options: FakeTracker())
    monkeypatch.setitem(rhythm._REGISTRY, "beat_this", lambda **options: FakeTracker())  # Standard
    monkeypatch.delenv("AUDIO2SCORE_CACHE", raising=False)
