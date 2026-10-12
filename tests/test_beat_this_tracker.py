import sys
import types

import numpy as np
import pytest

from audio2score import rhythm
from audio2score.rhythm.base import Beats
from audio2score.rhythm.beat_this import BeatThisTracker
from audio2score.transcribe.base import BackendUnavailableError, ModelDownloadError


class FakeAudio2Beats:
    calls: list = []
    fail = False

    def __init__(self, checkpoint_path="final0", device="cpu", float16=False, dbn=False):
        if FakeAudio2Beats.fail:
            raise RuntimeError("Gewichte kaputt")
        FakeAudio2Beats.calls.append((checkpoint_path, device, dbn))

    def __call__(self, signal, sr):
        # Downbeat liegt 10 ms neben dem Beat bei 1.0
        return np.array([0.5, 1.0, 1.5, 2.0]), np.array([1.01, 2.0, 2.0])


@pytest.fixture
def fake_package(monkeypatch):
    FakeAudio2Beats.calls = []
    FakeAudio2Beats.fail = False
    pkg = types.ModuleType("beat_this")
    inference = types.ModuleType("beat_this.inference")
    inference.Audio2Beats = FakeAudio2Beats
    pkg.inference = inference
    monkeypatch.setitem(sys.modules, "beat_this", pkg)
    monkeypatch.setitem(sys.modules, "beat_this.inference", inference)


def audio(seconds=1.0):
    return np.zeros(int(22_050 * seconds), dtype=np.float32)


def test_beats_are_python_floats_and_downbeats_snap_to_beats(fake_package):
    beats = BeatThisTracker().track(audio(), 22_050)
    assert beats.times == [0.5, 1.0, 1.5, 2.0]
    assert beats.downbeats == [1.0, 2.0]  # eingerastet, Dublette entfernt
    assert all(type(t) is float for t in beats.times + beats.downbeats)
    assert (beats.tracker, beats.tracker_version) == ("beat_this", BeatThisTracker().version)


def test_runs_on_cpu_without_dbn_and_loads_model_once(fake_package):
    t = BeatThisTracker()
    t.track(audio(), 22_050)
    t.track(audio(), 22_050)
    assert FakeAudio2Beats.calls == [("final0", "cpu", False)]


def test_constructing_does_not_load_the_model(fake_package):
    BeatThisTracker()
    assert FakeAudio2Beats.calls == []


def test_version_names_checkpoint():
    assert BeatThisTracker().version.endswith("-final0")


def test_wrong_sample_rate(fake_package):
    with pytest.raises(ValueError):
        BeatThisTracker().track(audio(), 16_000)


def test_missing_package_gives_install_hint(monkeypatch):
    monkeypatch.setitem(sys.modules, "beat_this", None)
    monkeypatch.setitem(sys.modules, "beat_this.inference", None)
    with pytest.raises(BackendUnavailableError, match="pip install"):
        BeatThisTracker().track(audio(), 22_050)


def test_weights_failure_becomes_download_error(fake_package):
    FakeAudio2Beats.fail = True
    with pytest.raises(ModelDownloadError, match="Gewichte kaputt"):
        BeatThisTracker().track(audio(), 22_050)


def test_no_beats_found_gives_empty_beats(fake_package, monkeypatch):
    monkeypatch.setattr(FakeAudio2Beats, "__call__", lambda self, s, sr: (np.array([]),) * 2)
    beats = BeatThisTracker().track(audio(), 22_050)
    assert beats.times == [] and beats.downbeats == []


def test_registry_default_and_unknown():
    assert rhythm.get_beat_tracker().name == "beat_this"
    with pytest.raises(ValueError, match="beat_this"):
        rhythm.get_beat_tracker("nope")


def test_beats_dict_roundtrip():
    b = Beats([0.5, 1.0], [0.5], "beat_this", "1.1.0-final0")
    assert Beats.from_dict(b.to_dict()) == b
