import pytest
import yaml
from typer.testing import CliRunner

from audio2score import rhythm
from audio2score.cli import app
from audio2score.pipeline import transcribe_file
from audio2score.transcribe.base import BackendUnavailableError
from score_fakes import FakeBackend, FakeTracker, install

runner = CliRunner()


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    install(monkeypatch)
    monkeypatch.delenv("AUDIO2SCORE_TESTSET", raising=False)


def entry(eid, **extra):
    return {
        "id": eid, "style": "classical", "source": "own", "quality": "studio",
        "license": "l", "origin": "o", **extra,
    }  # fmt: skip


@pytest.fixture
def setup(tmp_path, make_wav):
    """a: ok (4/4, 5 Soll-Takte) | b: nicht transkribiert | c: nur Referenz."""
    data = tmp_path / "data"
    data.mkdir()
    for i, name in enumerate("ab"):
        make_wav(f"data/{name}.wav", dur=1.0 + i * 0.1)
    (data / "a.txt").write_text(
        "".join(f"{i}\t{i}\t{'db' if i % 4 == 0 else 'b'}\n" for i in range(20))
    )
    entries = [
        entry("a", audio="a.wav", time_sig="4/4", ref_annotations="a.txt"),
        entry("b", audio="b.wav"),
        entry("c", ref_midi="c.mid"),
    ]
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(yaml.safe_dump({"version": 1, "data_dir": "data", "entries": entries}))
    transcribe_file(data / "a.wav", "fake", tmp_path / "c")
    FakeBackend.calls = 0
    return manifest


def run(setup, tmp_path, *extra):
    return runner.invoke(
        app,
        ["testset", "score", "-o", str(tmp_path / "out"), "--manifest", str(setup)]
        + ["--backend", "fake", "--cache-dir", str(tmp_path / "c"), *extra],
    )


def test_table_with_found_and_expected_values(setup, tmp_path):
    result = run(setup, tmp_path)
    assert result.exit_code == 0, result.output
    out = result.output
    assert "Taktart (ist/soll)" in out and "Takte (ist/soll)" in out and "Auftakt" in out
    row = next(line for line in out.splitlines() if line.startswith("a ") and "4/4" in line)
    assert "4/4 / 4/4" in row and "/ 5" in row and "ok" in row
    assert (tmp_path / "out" / "a.musicxml").is_file()


def test_skipped_pieces_are_listed_but_do_not_fail(setup, tmp_path):
    result = run(setup, tmp_path)
    assert "nicht transkribiert" in result.output
    assert "kein Audio" in result.output
    assert "1 ok, 2 übersprungen, 0 Fehler" in result.output
    assert FakeBackend.calls == 0


def test_failing_piece_gives_exit_code_1_but_others_run(setup, tmp_path):
    FakeTracker.fail_for = {1}
    result = run(setup, tmp_path)
    assert result.exit_code == 1
    assert "Beat-Fehler" in result.output
    assert "0 ok, 2 übersprungen, 1 Fehler" in result.output


def test_only_and_unknown_id(setup, tmp_path):
    ok = run(setup, tmp_path, "--only", "a")
    assert ok.exit_code == 0
    assert "1 ok, 0 übersprungen, 0 Fehler" in ok.output
    bad = run(setup, tmp_path, "--only", "zzz")
    assert bad.exit_code == 1 and "zzz" in bad.output


def test_unavailable_tracker_stops_with_exit_code_1(setup, tmp_path, monkeypatch):
    def broken(**options):
        raise BackendUnavailableError("beat_this fehlt. Installation: pip install beat_this")

    monkeypatch.setitem(rhythm._REGISTRY, "beat_this", broken)
    result = run(setup, tmp_path)
    assert result.exit_code == 1
    assert "pip install beat_this" in result.output
