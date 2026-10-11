import builtins
import sys
import types

import numpy as np
import pytest

from audio2score.transcribe import available_backends, get_transcriber
from audio2score.transcribe.base import BackendUnavailableError
from audio2score.transcribe.basic_pitch import BasicPitchTranscriber


def install_fake_basic_pitch(monkeypatch, events):
    pkg = types.ModuleType("basic_pitch")
    pkg.FilenameSuffix = types.SimpleNamespace(onnx="onnx")
    pkg.build_icassp_2022_model_path = lambda suffix: f"model.{suffix}"
    inference = types.ModuleType("basic_pitch.inference")
    seen = {}

    def predict(path, model_or_model_path):
        import soundfile as sf

        data, sr = sf.read(path)
        seen.update(sr=sr, n=len(data), model=model_or_model_path)
        return {}, None, events

    inference.predict = predict
    monkeypatch.setitem(sys.modules, "basic_pitch", pkg)
    monkeypatch.setitem(sys.modules, "basic_pitch.inference", inference)
    return seen


def test_event_mapping_and_onnx_model(monkeypatch):
    events = [
        (1.0, 2.0, 64, 0.5, [0]),
        (0.5, 1.0, 60, 0.0, [0]),  # Amplitude 0 -> Velocity 1
        (2.0, 3.0, 90, 1.0, [0]),  # 90 > 88: zulässig? Pitch <= 108 -> ja
        (3.0, 3.0, 62, 0.5, [0]),  # leer
        (3.0, 4.0, 10, 0.5, [0]),  # Pitch zu tief
    ]
    seen = install_fake_basic_pitch(monkeypatch, events)
    nl = BasicPitchTranscriber().transcribe(np.zeros(32_000, dtype=np.float32), 16_000)
    assert [(n.pitch, n.onset, n.offset, n.velocity) for n in nl.notes] == [
        (60, 0.5, 1.0, 1),
        (64, 1.0, 2.0, 64),
        (90, 2.0, 3.0, 127),
    ]
    assert nl.pedals == []
    assert nl.duration == 2.0
    assert seen["sr"] == 22_050
    assert seen["model"] == "model.onnx"


def test_missing_extra_gives_install_hint(monkeypatch):
    monkeypatch.delitem(sys.modules, "basic_pitch", raising=False)
    monkeypatch.delitem(sys.modules, "basic_pitch.inference", raising=False)
    real_import = builtins.__import__

    def fail(name, *args, **kwargs):
        if name.startswith("basic_pitch"):
            raise ImportError("No module named 'basic_pitch'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail)
    with pytest.raises(BackendUnavailableError) as exc:
        BasicPitchTranscriber().transcribe(np.zeros(16_000, dtype=np.float32), 16_000)
    assert "pip install -e .[basic-pitch]" in str(exc.value)
    assert "pip install --no-deps basic-pitch==0.4.0" in str(exc.value)


def test_registry():
    assert available_backends() == ["bytedance", "basic-pitch"]
    assert get_transcriber("basic-pitch").name == "basic-pitch"
    assert get_transcriber("bytedance").name == "bytedance"
    with pytest.raises(ValueError, match="Unbekanntes Backend"):
        get_transcriber("nope")
