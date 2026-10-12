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
