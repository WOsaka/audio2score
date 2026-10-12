import pytest

from audio2score import transcribe as transcribe_pkg
from audio2score.model import Note, NoteList
from audio2score.pipeline import cached_transcription, transcribe_file


class CountingBackend:
    name = "fake"
    version = "1"
    calls = 0

    def transcribe(self, audio, sample_rate):
        CountingBackend.calls += 1
        notes = [Note(60, 0.5, 1.5, 80), Note(64, 2.0, 2.01, 80)]  # zweite: zu kurz
        return NoteList(notes, [], 1.0, "fake", "1")


@pytest.fixture(autouse=True)
def fake_backend(monkeypatch):
    CountingBackend.calls = 0
    monkeypatch.setitem(transcribe_pkg._REGISTRY, "fake", lambda **options: CountingBackend())


def test_miss_returns_none_without_calling_backend(make_wav, tmp_path):
    audio = make_wav()
    assert cached_transcription(audio, "fake", tmp_path / "c") is None
    assert CountingBackend.calls == 0
    assert not (tmp_path / "c").exists()  # liest nur, schreibt nichts


def test_hit_returns_cleaned_result_without_calling_backend(make_wav, tmp_path):
    audio = make_wav()
    transcribe_file(audio, backend="fake", cache_dir=tmp_path / "c")
    assert CountingBackend.calls == 1
    result = cached_transcription(audio, "fake", tmp_path / "c")
    assert CountingBackend.calls == 1
    assert result.cache_hit is True
    assert result.raw_count == 2
    assert [n.pitch for n in result.notelist.notes] == [60]


def test_hit_without_cleanup_keeps_raw_notes(make_wav, tmp_path):
    audio = make_wav()
    transcribe_file(audio, backend="fake", cache_dir=tmp_path / "c")
    result = cached_transcription(audio, "fake", tmp_path / "c", do_cleanup=False)
    assert len(result.notelist.notes) == 2


def test_different_backend_version_is_a_miss(make_wav, tmp_path, monkeypatch):
    audio = make_wav()
    transcribe_file(audio, backend="fake", cache_dir=tmp_path / "c")
    newer = type("Newer", (CountingBackend,), {"version": "2"})
    monkeypatch.setitem(transcribe_pkg._REGISTRY, "fake", lambda **options: newer())
    assert cached_transcription(audio, "fake", tmp_path / "c") is None


class CountingTracker:
    name = "fake-tracker"
    version = "1"
    calls = 0

    def track(self, audio, sample_rate):
        from audio2score.rhythm.base import Beats

        CountingTracker.calls += 1
        assert sample_rate == 22_050
        return Beats([0.5, 1.0, 1.5], [0.5], self.name, self.version)


def test_cached_beats_miss_does_not_call_tracker(make_wav, tmp_path):
    from audio2score.pipeline import cached_beats

    CountingTracker.calls = 0
    assert cached_beats(make_wav(), tmp_path / "c", CountingTracker()) is None
    assert CountingTracker.calls == 0
    assert not (tmp_path / "c").exists()


def test_detect_beats_computes_once_then_hits_cache(make_wav, tmp_path):
    from audio2score.pipeline import cached_beats, detect_beats

    CountingTracker.calls = 0
    audio = make_wav()
    seen = []
    beats, hit = detect_beats(
        audio, tmp_path / "c", tracker=CountingTracker(), on_beats=lambda: seen.append(1)
    )
    assert (hit, CountingTracker.calls, seen) == (False, 1, [1])
    again, hit = detect_beats(
        audio, tmp_path / "c", tracker=CountingTracker(), on_beats=lambda: seen.append(1)
    )
    assert (hit, CountingTracker.calls, seen) == (True, 1, [1])
    assert again == beats
    assert cached_beats(audio, tmp_path / "c", CountingTracker()) == beats


def test_detect_beats_without_cache_always_computes_and_writes_nothing(make_wav, tmp_path):
    from audio2score.pipeline import detect_beats

    CountingTracker.calls = 0
    for _ in range(2):
        _, hit = detect_beats(
            make_wav(), tmp_path / "c", use_cache=False, tracker=CountingTracker()
        )
        assert hit is False
    assert CountingTracker.calls == 2
    assert not (tmp_path / "c").exists()


def test_detect_beats_missing_file(tmp_path):
    from audio2score.audio.load import AudioLoadError
    from audio2score.pipeline import detect_beats

    with pytest.raises(AudioLoadError):
        detect_beats(tmp_path / "x.wav", tmp_path / "c", tracker=CountingTracker())
