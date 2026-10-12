import pytest
import yaml

from audio2score.pipeline import transcribe_file
from audio2score.testset.manifest import load_manifest
from audio2score.testset.run import score_all
from score_fakes import FakeBackend, FakeTracker, install


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    install(monkeypatch)


def entry(eid, **extra):
    return {
        "id": eid, "style": "classical", "source": "own", "quality": "studio",
        "license": "l", "origin": "o", **extra,
    }  # fmt: skip


@pytest.fixture
def manifest(tmp_path, make_wav):
    """a: ok, 4/4 mit 5 Soll-Takten | b: nicht transkribiert | c: ok, Soll 3/4 (weicht ab)
    | d: Beat-Erkennung scheitert | e: ohne Audio | f: Audio fehlt."""
    data = tmp_path / "data"
    data.mkdir()
    for i, name in enumerate("abcd"):
        make_wav(f"data/{name}.wav", dur=1.0 + i * 0.1)  # verschiedene Hashes
    ann = "".join(f"{i}.0\t{i}.0\t{'db' if i % 4 == 0 else 'b'}\n" for i in range(20))
    (data / "a.txt").write_text(ann + "9.5\t9.5\tbR\n")  # 5 Downbeats (i = 0,4,8,12,16)
    entries = [
        entry("a", audio="a.wav", time_sig="4/4", ref_annotations="a.txt"),
        entry("b", audio="b.wav"),
        entry("c", audio="c.wav", time_sig="3/4"),
        entry("d", audio="d.wav"),
        entry("e", ref_midi="e.mid"),
        entry("f", audio="gone.wav"),
    ]
    path = tmp_path / "manifest.yaml"
    path.write_text(yaml.safe_dump({"version": 1, "data_dir": "data", "entries": entries}))
    return load_manifest(path)


@pytest.fixture
def cache(tmp_path, manifest):
    for entry_id in "acd":  # b bleibt ohne Noten im Cache
        audio = next(e.audio for e in manifest.entries if e.id == entry_id)
        transcribe_file(audio, "fake", tmp_path / "c")
    FakeBackend.calls = 0
    return tmp_path / "c"


def rows_by_id(rows):
    return {r.id: r for r in rows}


def test_statuses(manifest, cache, tmp_path):
    rows = rows_by_id(score_all(manifest, "fake", cache, tmp_path / "out"))
    assert {k: r.status for k, r in rows.items()} == {
        "a": "ok", "b": "not_transcribed", "c": "ok", "d": "ok", "e": "skipped", "f": "missing",
    }  # fmt: skip


def test_notes_come_only_from_the_cache(manifest, cache, tmp_path):
    score_all(manifest, "fake", cache, tmp_path / "out")
    assert FakeBackend.calls == 0
    assert FakeTracker.calls == 3  # nur a, c, d; b wird nicht einmal beat-erkannt


def test_found_and_expected_values(manifest, cache, tmp_path):
    rows = rows_by_id(score_all(manifest, "fake", cache, tmp_path / "out"))
    a, c = rows["a"], rows["c"]
    assert (a.time_sig, a.expected_time_sig) == ("4/4", "4/4")
    assert a.expected_bars == 5 and a.bars >= 1
    assert a.pickup is False
    assert (c.time_sig, c.expected_time_sig, c.expected_bars) == ("4/4", "3/4", None)


def test_manifest_time_sig_is_not_used_as_a_hint(manifest, cache, tmp_path):
    rows = rows_by_id(score_all(manifest, "fake", cache, tmp_path / "out"))
    assert rows["c"].time_sig == "4/4"  # erkannt, nicht die Soll-Angabe 3/4


def test_every_scored_piece_is_written_and_readable(manifest, cache, tmp_path):
    score_all(manifest, "fake", cache, tmp_path / "out")
    for name in "acd":
        assert (tmp_path / "out" / f"{name}.musicxml").is_file()


def test_a_failing_piece_does_not_stop_the_others(manifest, cache, tmp_path):
    FakeTracker.fail_for = {2}  # zweiter Aufruf = c
    rows = score_all(manifest, "fake", cache, tmp_path / "out")
    by_id = rows_by_id(rows)
    assert by_id["c"].status == "failed" and "Beat-Fehler" in by_id["c"].message
    assert by_id["a"].status == "ok" and by_id["d"].status == "ok"


def test_unreadable_musicxml_counts_as_failure(manifest, cache, tmp_path, monkeypatch):
    import audio2score.testset.run as run_mod

    def broken(path):
        raise ValueError("kaputtes XML")

    monkeypatch.setattr(run_mod, "_reread", broken)
    rows = score_all(manifest, "fake", cache, tmp_path / "out")
    assert rows[0].status == "failed" and "kaputtes XML" in rows[0].message


def test_only_filter_and_events(manifest, cache, tmp_path):
    starts, dones = [], []
    rows = score_all(
        manifest, "fake", cache, tmp_path / "out", only=["a", "e"],
        on_start=lambda i, n, e: starts.append((i, n, e.id)),
        on_result=lambda i, n, r: dones.append((i, r.status)),
    )  # fmt: skip
    assert [r.id for r in rows] == ["a", "e"]
    assert starts == [(1, 2, "a"), (2, 2, "e")]
    assert dones == [(1, "ok"), (2, "skipped")]


def test_beats_are_cached_for_the_next_run(manifest, cache, tmp_path):
    score_all(manifest, "fake", cache, tmp_path / "out")
    calls = FakeTracker.calls
    score_all(manifest, "fake", cache, tmp_path / "out")
    assert FakeTracker.calls == calls
