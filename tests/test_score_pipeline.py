import json

import pytest
from music21 import converter

from audio2score.audio.load import AudioLoadError
from audio2score.pipeline import score_file
from audio2score.rhythm.base import RhythmError
from score_fakes import FakeBackend, FakeTracker, install


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    install(monkeypatch)


def run(audio, tmp_path, **kwargs):
    kwargs.setdefault("backend", "fake")
    kwargs.setdefault("cache_dir", tmp_path / "c")
    kwargs.setdefault("tracker", FakeTracker())
    return score_file(audio, tmp_path / "out", **kwargs)


def test_writes_the_three_files_named_after_the_audio(make_wav, tmp_path):
    audio = make_wav("stück.wav")
    result = run(audio, tmp_path)
    out = tmp_path / "out"
    assert result.musicxml == out / "stück.musicxml"
    assert result.midi == out / "stück.quantized.mid"
    assert result.beats_json == out / "stück.beats.json"
    assert all(p.is_file() for p in (result.musicxml, result.midi, result.beats_json))
    assert len(converter.parse(result.musicxml).parts) == 2
    assert json.loads(result.beats_json.read_text(encoding="utf-8"))["audio"] == "stück.wav"


def test_result_describes_grid_notes_and_cache_state(make_wav, tmp_path):
    result = run(make_wav(), tmp_path)
    assert (result.grid.meter.numerator, result.grid.meter.source) == (4, "detected")
    assert result.bars == result.grid.bars >= 2
    assert result.right_notes == 8 and result.left_notes == 1
    assert (result.notes_cache_hit, result.beats_cache_hit) == (False, False)
    assert result.elapsed > 0


def test_second_run_needs_neither_backend_nor_tracker(make_wav, tmp_path):
    audio = make_wav()
    run(audio, tmp_path)
    assert (FakeBackend.calls, FakeTracker.calls) == (1, 1)
    second = run(audio, tmp_path)
    assert (FakeBackend.calls, FakeTracker.calls) == (1, 1)
    assert (second.notes_cache_hit, second.beats_cache_hit) == (True, True)


def test_progress_callbacks_fire_only_on_cache_misses(make_wav, tmp_path):
    audio, seen = make_wav(), []
    kwargs = {
        "on_transcribe": lambda: seen.append("notes"),
        "on_beats": lambda: seen.append("beats"),
    }
    run(audio, tmp_path, **kwargs)
    run(audio, tmp_path, **kwargs)
    assert seen == ["notes", "beats"]


def test_no_cache_always_computes_and_writes_no_cache(make_wav, tmp_path):
    audio = make_wav()
    run(audio, tmp_path, use_cache=False)
    run(audio, tmp_path, use_cache=False)
    assert (FakeBackend.calls, FakeTracker.calls) == (2, 2)
    assert not (tmp_path / "c").exists()


def test_given_time_sig_overrides_detection(make_wav, tmp_path):
    result = run(make_wav(), tmp_path, time_sig=(3, 4))
    assert (result.grid.meter.numerator, result.grid.meter.source) == (3, "given")
    back = converter.parse(result.musicxml)
    assert back.parts[0].recurse().getElementsByClass("TimeSignature")[0].ratioString == "3/4"


def test_warnings_are_collected(make_wav, tmp_path):
    FakeTracker.downbeat_every = 100  # nur der erste Downbeat → keine Taktlängen ableitbar
    result = run(make_wav(), tmp_path)
    assert any("Downbeat" in w for w in result.warnings)


def test_no_notes_fails_before_detecting_beats_and_writes_nothing(make_wav, tmp_path):
    FakeBackend.notes = []
    with pytest.raises(RhythmError, match="Noten"):
        run(make_wav(), tmp_path)
    assert FakeTracker.calls == 0
    assert not (tmp_path / "out").exists()


def test_too_few_beats_fails_and_writes_nothing(make_wav, tmp_path):
    FakeTracker.n_beats = 3
    with pytest.raises(RhythmError, match="Beats"):
        run(make_wav(), tmp_path)
    assert not (tmp_path / "out").exists()


def test_missing_audio(tmp_path):
    with pytest.raises(AudioLoadError):
        run(tmp_path / "nope.wav", tmp_path)


def test_target_folder_is_created(make_wav, tmp_path):
    result = score_file(
        make_wav(),
        tmp_path / "a" / "b",
        backend="fake",
        cache_dir=tmp_path / "c",
        tracker=FakeTracker(),
    )
    assert result.musicxml.parent == tmp_path / "a" / "b"
