import pytest
from typer.testing import CliRunner

from audio2score import rhythm
from audio2score.cli import app
from audio2score.transcribe.base import BackendUnavailableError
from score_fakes import FakeBackend, FakeTracker, install

runner = CliRunner()


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    install(monkeypatch)


def run(audio, tmp_path, *extra):
    return runner.invoke(
        app,
        ["score", str(audio), "-o", str(tmp_path / "out"), "--backend", "fake"]
        + ["--cache-dir", str(tmp_path / "c"), *extra],
    )


def test_first_run_prints_summary_and_writes_three_files(make_wav, tmp_path):
    audio = make_wav("stück.wav")
    result = run(audio, tmp_path)
    assert result.exit_code == 0, result.output
    out = result.output
    assert "Backend: fake" in out
    assert "Transkribiere ..." in out and "Erkenne Beats ..." in out
    assert "Taktart: 4/4 (erkannt)" in out
    assert "Tempo: 120 BPM" in out
    assert "Takte: " in out and "Auftakt: nein" in out
    assert "Noten: rechte Hand 8, linke Hand 1" in out
    for name in ("stück.musicxml", "stück.quantized.mid", "stück.beats.json"):
        assert name in out
        assert (tmp_path / "out" / name).is_file()


def test_second_run_uses_both_caches_silently(make_wav, tmp_path):
    audio = make_wav()
    run(audio, tmp_path)
    result = run(audio, tmp_path)
    assert result.exit_code == 0
    assert "Transkribiere" not in result.output and "Erkenne Beats" not in result.output
    assert "Noten und Beats aus Cache" in result.output
    assert (FakeBackend.calls, FakeTracker.calls) == (1, 1)


def test_given_time_sig(make_wav, tmp_path):
    result = run(make_wav(), tmp_path, "--time-sig", "3/4")
    assert result.exit_code == 0, result.output
    assert "Taktart: 3/4 (vorgegeben)" in result.output


def test_default_time_sig_is_labelled(make_wav, tmp_path):
    FakeTracker.downbeat_every = 100
    result = run(make_wav(), tmp_path)
    assert "Taktart: 4/4 (Standard)" in result.output
    assert "Warnung: Keine Downbeats erkannt" in result.output


def test_pickup_is_reported(make_wav, tmp_path):
    FakeBackend.notes = [n for n in FakeBackend.notes if n.pitch > 60]
    FakeBackend.notes = [
        type(n)(n.pitch, n.onset + 1.0, n.offset + 1.0, n.velocity) for n in FakeBackend.notes
    ]
    result = run(make_wav(), tmp_path, "--time-sig", "3/4")
    assert "Auftakt: ja" in result.output


def test_invalid_time_sig_lists_allowed_values(make_wav, tmp_path):
    result = run(make_wav(), tmp_path, "--time-sig", "5/4")
    assert result.exit_code == 2
    assert "12/8" in result.output
    assert FakeBackend.calls == 0


def test_missing_audio_exits_with_1(tmp_path):
    result = run(tmp_path / "nope.wav", tmp_path)
    assert result.exit_code == 1
    assert "Fehler" in result.output


def test_no_notes_exits_with_1_and_writes_nothing(make_wav, tmp_path):
    FakeBackend.notes = []
    result = run(make_wav(), tmp_path)
    assert result.exit_code == 1
    assert "Keine Noten" in result.output
    assert not (tmp_path / "out").exists()


def test_too_few_beats_exits_with_1(make_wav, tmp_path):
    FakeTracker.n_beats = 3
    result = run(make_wav(), tmp_path)
    assert result.exit_code == 1
    assert "Beats" in result.output
    assert not (tmp_path / "out").exists()


def test_unavailable_tracker_exits_with_1(make_wav, tmp_path, monkeypatch):
    def broken(**options):
        raise BackendUnavailableError("beat_this fehlt. Installation: pip install beat_this")

    monkeypatch.setitem(rhythm._REGISTRY, "beat_this", broken)
    result = run(make_wav(), tmp_path)
    assert result.exit_code == 1
    assert "pip install beat_this" in result.output


def test_unknown_backend_is_rejected(make_wav, tmp_path):
    result = runner.invoke(
        app, ["score", str(make_wav()), "-o", str(tmp_path / "o"), "--backend", "nope"]
    )
    assert result.exit_code == 2
