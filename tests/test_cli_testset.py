import pretty_midi
import pytest
import yaml
from typer.testing import CliRunner

from audio2score import transcribe as transcribe_pkg
from audio2score.cli import app
from audio2score.model import Note, NoteList
from audio2score.testset import fetch as fetch_mod

runner = CliRunner()


class FakeBackend:
    name = "fake"
    version = "1"
    calls = 0
    fail_for: set[int] = set()

    def transcribe(self, audio, sample_rate):
        FakeBackend.calls += 1
        if FakeBackend.calls in FakeBackend.fail_for:
            raise RuntimeError("Modellfehler")
        notes = [Note(60, 0.5, 1.5, 80), Note(72, 1.0, 2.0, 70)]
        return NoteList(notes, [], 1.0, "fake", "1")


@pytest.fixture(autouse=True)
def fake_backend(monkeypatch):
    FakeBackend.calls = 0
    FakeBackend.fail_for = set()
    monkeypatch.setitem(transcribe_pkg._REGISTRY, "fake", lambda **options: FakeBackend())
    monkeypatch.delenv("AUDIO2SCORE_TESTSET", raising=False)
    monkeypatch.delenv("AUDIO2SCORE_CACHE", raising=False)


def write_midi(path, notes):
    midi = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(program=0)
    inst.notes += [pretty_midi.Note(80, p, s, e) for p, s, e in notes]
    midi.instruments.append(inst)
    midi.write(str(path))


def entry(eid, **extra):
    return {
        "id": eid, "style": "classical", "source": "own", "quality": "phone",
        "license": "l", "origin": "o", **extra,
    }  # fmt: skip


@pytest.fixture
def env(tmp_path, make_wav):
    """Manifest mit a (Audio + MIDI), b (Audio ohne Referenz)."""
    data = tmp_path / "data"
    data.mkdir()
    make_wav("data/a.wav", dur=1.0)
    make_wav("data/b.wav", dur=1.2)
    write_midi(data / "a.mid", [(60, 0.5, 1.5), (72, 1.0, 2.0)])
    path = tmp_path / "manifest.yaml"
    entries = [entry("a", audio="a.wav", ref_midi="a.mid"), entry("b", audio="b.wav")]

    def write(entries=entries, **top):
        doc = {"version": 1, "data_dir": "data", "entries": entries, **top}
        path.write_text(yaml.safe_dump(doc), encoding="utf-8")

    write()
    env = type("Env", (), {})()
    env.path, env.cache, env.write, env.data = path, tmp_path / "cache", write, data
    return env


def run(env, command, *args, cache=True):
    extra = ["--cache-dir", str(env.cache)] if cache else []
    return runner.invoke(
        app, ["testset", command, "--manifest", str(env.path), *extra, *map(str, args)]
    )


def test_check_ok(env):
    result = runner.invoke(app, ["testset", "check", "--manifest", str(env.path)])
    assert result.exit_code == 0, result.output
    assert "OK" in result.output and "a" in result.output
    assert "2 Einträge" in result.output


def test_check_reports_missing_file_with_reason(env):
    (env.data / "a.mid").unlink()
    result = runner.invoke(app, ["testset", "check", "--manifest", str(env.path)])
    assert result.exit_code == 1
    assert "FEHLER" in result.output and "a.mid" in result.output and "Datei fehlt" in result.output


def test_check_reports_manifest_errors(env):
    env.write([entry("a", audio="a.wav", style="rock")])
    result = runner.invoke(app, ["testset", "check", "--manifest", str(env.path)])
    assert result.exit_code == 1
    assert "style" in result.output and "classical" in result.output


def test_manifest_from_env_var(env, monkeypatch):
    monkeypatch.setenv("AUDIO2SCORE_TESTSET", str(env.path))
    assert runner.invoke(app, ["testset", "check"]).exit_code == 0


def test_missing_manifest_is_a_clean_error(tmp_path):
    result = runner.invoke(app, ["testset", "check", "--manifest", str(tmp_path / "nope.yaml")])
    assert result.exit_code == 1 and "nope.yaml" in result.output


def test_data_dir_option(env, tmp_path):
    result = runner.invoke(
        app, ["testset", "check", "--manifest", str(env.path), "--data-dir", str(tmp_path / "x")]
    )
    assert result.exit_code == 1  # dort liegen keine Dateien


def test_fetch_skips_entries_without_fetch_block(env):
    result = runner.invoke(app, ["testset", "fetch", "--manifest", str(env.path)])
    assert result.exit_code == 0, result.output
    assert "übersprungen" in result.output


def test_fetch_failure_gives_exit_1_and_names_the_piece(env, monkeypatch):
    monkeypatch.setattr(fetch_mod, "ASAP_BASE_URL", "http://127.0.0.1:1/asap")
    monkeypatch.setattr(fetch_mod, "RETRY_DELAY", 0.0)
    env.write(
        [
            entry(
                "asap-x", source="asap", ref_midi="p.mid",
                fetch={"asap_folder": "Bach/X", "asap_performance": "Y"},
            ),
            entry("b", audio="b.wav"),
        ]
    )  # fmt: skip
    result = runner.invoke(app, ["testset", "fetch", "--manifest", str(env.path)])
    assert result.exit_code == 1
    assert "asap-x" in result.output and "FEHLER" in result.output


def test_unknown_only_id_is_an_error(env):
    result = run(env, "transcribe", "--backend", "fake", "--only", "zzz")
    assert result.exit_code == 1 and "zzz" in result.output


def test_unknown_backend(env):
    assert run(env, "transcribe", "--backend", "nope").exit_code == 2


def test_transcribe_then_resume_from_cache(env):
    first = run(env, "transcribe", "--backend", "fake")
    assert first.exit_code == 0, first.output
    assert "[1/2] a" in first.output and "transkribiert" in first.output
    assert FakeBackend.calls == 2
    second = run(env, "transcribe", "--backend", "fake")
    assert second.exit_code == 0
    assert second.output.count("aus Cache") == 2
    assert FakeBackend.calls == 2


def test_transcribe_failure_exit_1_but_continues(env):
    FakeBackend.fail_for = {1}
    result = run(env, "transcribe", "--backend", "fake")
    assert result.exit_code == 1
    assert "FEHLER" in result.output and "Modellfehler" in result.output
    assert "[2/2] b" in result.output and FakeBackend.calls == 2


def test_transcribe_warns_about_missing_file_and_exits_0(env):
    (env.data / "b.wav").unlink()
    result = run(env, "transcribe", "--backend", "fake")
    assert result.exit_code == 0
    assert "WARNUNG" in result.output and "b.wav" in result.output


def test_baseline_table_and_means_without_model_run(env):
    run(env, "transcribe", "--backend", "fake")
    FakeBackend.calls = 0
    result = run(env, "baseline", "--backend", "fake")
    assert result.exit_code == 0, result.output
    assert "1.000" in result.output  # F1 von a
    assert "keine Referenz" in result.output  # b
    assert "classical" in result.output and "phone" in result.output  # Mittelwerte
    assert "2/2" in result.output
    assert FakeBackend.calls == 0


def test_baseline_without_cache_hints_at_transcribe(env):
    result = run(env, "baseline", "--backend", "fake")
    assert result.exit_code == 0
    assert "nicht transkribiert" in result.output
    assert "testset transcribe" in result.output
    assert FakeBackend.calls == 0
