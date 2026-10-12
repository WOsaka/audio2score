import sys

import pretty_midi
import pytest
from typer.testing import CliRunner

from audio2score import transcribe as transcribe_pkg
from audio2score.cli import app, note_name
from audio2score.model import Note, NoteList, PedalEvent

runner = CliRunner()


class FakeBackend:
    name = "fake"
    version = "1"
    calls = 0
    notes = [
        Note(60, 0.5, 1.5, 80),
        Note(72, 1.0, 2.0, 70),
        Note(64, 2.0, 2.01, 80),  # zu kurz: fällt beim Aufräumen weg
    ]

    def transcribe(self, audio, sample_rate):
        FakeBackend.calls += 1
        return NoteList(list(FakeBackend.notes), [PedalEvent(0.4, 2.5)], 1.0, "fake", "1")


@pytest.fixture(autouse=True)
def fake_backend(monkeypatch):
    FakeBackend.calls = 0
    monkeypatch.setitem(transcribe_pkg._REGISTRY, "fake", lambda **options: FakeBackend())
    monkeypatch.delenv("AUDIO2SCORE_CACHE", raising=False)


def run(*args):
    return runner.invoke(app, ["transcribe", *map(str, args)])


@pytest.fixture
def audio(make_wav):
    return make_wav()


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.startswith("audio2score ")


def test_first_run_writes_midi_and_summary(audio, tmp_path):
    out = tmp_path / "out" / "a.mid"
    result = run(audio, "-o", out, "--backend", "fake", "--cache-dir", tmp_path / "c")
    assert result.exit_code == 0, result.output
    notes = pretty_midi.PrettyMIDI(str(out)).instruments[0].notes
    assert sorted(n.pitch for n in notes) == [60, 72]
    assert "3 roh, 2 nach dem Aufräumen" in result.output
    assert "C4–C5" in result.output
    assert "Pedal-Events: 1" in result.output
    assert "aus Cache" not in result.output
    assert FakeBackend.calls == 1


def test_second_run_uses_cache_without_calling_backend(audio, tmp_path):
    args = (audio, "-o", tmp_path / "a.mid", "--backend", "fake", "--cache-dir", tmp_path / "c")
    run(*args)
    result = run(*args)
    assert result.exit_code == 0
    assert FakeBackend.calls == 1
    assert "aus Cache" in result.output


def test_cache_hit_does_not_load_audio(audio, tmp_path, monkeypatch):
    args = (audio, "-o", tmp_path / "a.mid", "--backend", "fake", "--cache-dir", tmp_path / "c")
    run(*args)

    def boom(*a, **k):
        raise AssertionError("Audio darf bei Cache-Treffer nicht geladen werden")

    monkeypatch.setattr("audio2score.pipeline.load_audio", boom)
    assert run(*args).exit_code == 0


def test_no_cache_neither_reads_nor_writes(audio, tmp_path):
    cache_dir = tmp_path / "c"
    args = (audio, "-o", tmp_path / "a.mid", "--backend", "fake", "--cache-dir", cache_dir)
    run(*args, "--no-cache")
    run(*args, "--no-cache")
    assert FakeBackend.calls == 2
    assert not cache_dir.exists() or not list(cache_dir.glob("*.json"))


def test_no_cleanup_keeps_raw_notes_and_cache_still_holds_raw(audio, tmp_path):
    base = (audio, "--backend", "fake", "--cache-dir", tmp_path / "c")
    cleaned = tmp_path / "cleaned.mid"
    raw = tmp_path / "raw.mid"
    run(*base, "-o", cleaned)
    result = run(*base, "-o", raw, "--no-cleanup")
    assert FakeBackend.calls == 1  # --no-cleanup funktioniert ohne erneuten Modelllauf
    assert "aus Cache" in result.output
    assert len(pretty_midi.PrettyMIDI(str(cleaned)).instruments[0].notes) == 2
    assert len(pretty_midi.PrettyMIDI(str(raw)).instruments[0].notes) == 3


def test_cache_dir_option_beats_env(audio, tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIO2SCORE_CACHE", str(tmp_path / "env"))
    run(audio, "-o", tmp_path / "a.mid", "--backend", "fake")
    assert list((tmp_path / "env").glob("*.json"))
    run(audio, "-o", tmp_path / "a.mid", "--backend", "fake", "--cache-dir", tmp_path / "opt")
    assert list((tmp_path / "opt").glob("*.json"))


def test_missing_file(tmp_path):
    result = run(tmp_path / "nope.wav", "-o", tmp_path / "a.mid", "--backend", "fake")
    assert result.exit_code == 1
    assert "nicht gefunden" in result.stderr
    assert "Traceback" not in result.output + result.stderr


def test_unreadable_file(tmp_path):
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"kein audio")
    result = run(bad, "-o", tmp_path / "a.mid", "--backend", "fake", "--cache-dir", tmp_path)
    assert result.exit_code == 1
    assert "Traceback" not in result.output + result.stderr


def test_basic_pitch_not_installed(audio, tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "basic_pitch", None)  # Import schlägt fehl
    result = run(audio, "-o", tmp_path / "a.mid", "--backend", "basic-pitch", "--no-cache")
    assert result.exit_code == 1
    assert "pip install -e .[basic-pitch]" in result.stderr
    assert "--no-deps basic-pitch==0.4.0" in result.stderr


def test_empty_result_gives_empty_midi_and_warning(audio, tmp_path, monkeypatch):
    monkeypatch.setattr(FakeBackend, "notes", [])
    out = tmp_path / "a.mid"
    result = run(audio, "-o", out, "--backend", "fake", "--no-cache")
    assert result.exit_code == 0
    assert "keine Noten" in result.stderr
    assert out.is_file()
    assert all(not i.notes for i in pretty_midi.PrettyMIDI(str(out)).instruments)


def test_unknown_backend(audio, tmp_path):
    result = run(audio, "-o", tmp_path / "a.mid", "--backend", "nope")
    assert result.exit_code != 0


def test_note_names():
    assert note_name(60) == "C4"
    assert note_name(21) == "A0"
    assert note_name(108) == "C8"
    assert note_name(61) == "C#4"
