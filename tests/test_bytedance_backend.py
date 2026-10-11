import sys
import types

import numpy as np
import pytest

from audio2score.transcribe import bytedance
from audio2score.transcribe.base import ModelDownloadError
from audio2score.transcribe.bytedance import ByteDanceTranscriber


class FakePiano:
    calls: list = []

    def __init__(self, device, checkpoint_path):
        FakePiano.calls.append((device, checkpoint_path))

    def transcribe(self, audio, midi_path):
        assert midi_path is None
        return {
            "est_note_events": [
                {"onset_time": 1.0, "offset_time": 2.0, "midi_note": 64, "velocity": 70},
                {"onset_time": 0.5, "offset_time": 1.5, "midi_note": 60, "velocity": 0},
                {"onset_time": 3.0, "offset_time": 3.0, "midi_note": 62, "velocity": 50},  # leer
                {"onset_time": 3.0, "offset_time": 4.0, "midi_note": 10, "velocity": 50},  # Pitch
            ],
            "est_pedal_events": [{"onset_time": 0.4, "offset_time": 2.2}],
        }


@pytest.fixture
def fake_package(monkeypatch):
    FakePiano.calls = []
    mod = types.ModuleType("piano_transcription_inference")
    mod.PianoTranscription = FakePiano
    monkeypatch.setitem(sys.modules, "piano_transcription_inference", mod)


@pytest.fixture
def small_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(bytedance, "MIN_CHECKPOINT_BYTES", 10)
    path = tmp_path / "ck.pth"
    path.write_bytes(b"x" * 20)
    return path


def test_event_mapping(fake_package, small_checkpoint):
    t = ByteDanceTranscriber(checkpoint=small_checkpoint)
    nl = t.transcribe(np.zeros(32_000, dtype=np.float32), 16_000)
    assert [(n.pitch, n.onset, n.offset, n.velocity) for n in nl.notes] == [
        (60, 0.5, 1.5, 1),  # Velocity 0 wird auf 1 angehoben
        (64, 1.0, 2.0, 70),
    ]
    assert [(p.onset, p.offset) for p in nl.pedals] == [(0.4, 2.2)]
    assert nl.duration == 2.0
    assert (nl.backend, nl.backend_version) == (t.name, t.version)


def test_runs_on_cpu_with_given_checkpoint_and_loads_once(fake_package, small_checkpoint):
    t = ByteDanceTranscriber(checkpoint=small_checkpoint)
    audio = np.zeros(16_000, dtype=np.float32)
    t.transcribe(audio, 16_000)
    t.transcribe(audio, 16_000)
    assert FakePiano.calls == [("cpu", str(small_checkpoint))]


def test_wrong_sample_rate(fake_package, small_checkpoint):
    with pytest.raises(ValueError):
        ByteDanceTranscriber(checkpoint=small_checkpoint).transcribe(np.zeros(10), 44_100)


def test_checkpoint_resolution_order(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIO2SCORE_CHECKPOINT", str(tmp_path / "env.pth"))
    assert bytedance.resolve_checkpoint(tmp_path / "opt.pth") == tmp_path / "opt.pth"
    assert bytedance.resolve_checkpoint(None) == tmp_path / "env.pth"
    monkeypatch.delenv("AUDIO2SCORE_CHECKPOINT")
    default = bytedance.resolve_checkpoint(None)
    assert default.name == "note_F1=0.9677_pedal_F1=0.9186.pth"
    assert default.parent.name == "piano_transcription_inference_data"


def test_download_atomic_with_progress(tmp_path):
    src = tmp_path / "src.bin"
    src.write_bytes(b"a" * 3_000_000)
    dest = tmp_path / "out" / "m.pth"
    seen = []
    bytedance.download_checkpoint(
        dest, src.as_uri(), lambda done, total: seen.append((done, total))
    )
    assert dest.read_bytes() == src.read_bytes()
    assert not dest.with_name("m.pth.part").exists()
    assert seen[-1] == (3_000_000, 3_000_000)


def test_download_failure_gives_url_and_leaves_no_files(tmp_path):
    dest = tmp_path / "m.pth"
    url = (tmp_path / "missing.bin").as_uri()
    with pytest.raises(ModelDownloadError) as exc:
        bytedance.download_checkpoint(dest, url)
    assert url in str(exc.value)
    assert str(dest) in str(exc.value)
    assert not dest.exists()
    assert not dest.with_name("m.pth.part").exists()


def test_ensure_checkpoint_redownloads_when_too_small(tmp_path, monkeypatch):
    monkeypatch.setattr(bytedance, "MIN_CHECKPOINT_BYTES", 10)
    src = tmp_path / "src.bin"
    src.write_bytes(b"b" * 50)
    monkeypatch.setattr(bytedance, "CHECKPOINT_URL", src.as_uri())
    dest = tmp_path / "m.pth"
    dest.write_bytes(b"tiny")
    assert bytedance.ensure_checkpoint(dest).stat().st_size == 50
