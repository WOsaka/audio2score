import pretty_midi
import pytest
import yaml

from audio2score import transcribe as transcribe_pkg
from audio2score.model import Note, NoteList, PedalEvent
from audio2score.testset.manifest import load_manifest
from audio2score.testset.run import baseline, group_means, transcribe_all


class FakeBackend:
    name = "fake"
    version = "1"
    calls = 0
    fail_for: set[int] = set()
    notes = [
        Note(60, 0.5, 1.5, 80),
        Note(72, 1.0, 2.0, 70),
        Note(64, 2.0, 2.01, 80),  # zu kurz: fällt beim Aufräumen weg
    ]

    def transcribe(self, audio, sample_rate):
        FakeBackend.calls += 1
        if FakeBackend.calls in FakeBackend.fail_for:
            raise RuntimeError("Modellfehler")
        return NoteList(list(FakeBackend.notes), [PedalEvent(0.4, 2.5)], 1.0, "fake", "1")


@pytest.fixture(autouse=True)
def fake_backend(monkeypatch):
    FakeBackend.calls = 0
    FakeBackend.fail_for = set()
    monkeypatch.setitem(transcribe_pkg._REGISTRY, "fake", lambda **options: FakeBackend())


def write_midi(path, notes):
    midi = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(program=0)
    inst.notes += [pretty_midi.Note(80, p, s, e) for p, s, e in notes]
    midi.instruments.append(inst)
    path.parent.mkdir(parents=True, exist_ok=True)
    midi.write(str(path))


def entry(eid, style="classical", quality="studio", **extra):
    return {
        "id": eid, "style": style, "source": "own", "quality": quality,
        "license": "l", "origin": "o", **extra,
    }  # fmt: skip


@pytest.fixture
def manifest(tmp_path, make_wav):
    """a: perfekte Referenz | b: Referenz mit Zusatznote | c: ohne Referenz | d: nur MIDI
    | e: Audio fehlt | f: Referenz-MIDI fehlt."""
    data = tmp_path / "data"
    data.mkdir()
    for name in "abcef":
        make_wav(f"data/{name}.wav", dur=1.0 + "abcef".index(name) * 0.1)  # verschiedene Hashes
    write_midi(data / "a.mid", [(60, 0.5, 1.5), (72, 1.0, 2.0)])
    write_midi(data / "b.mid", [(60, 0.5, 1.5), (72, 1.0, 2.0), (67, 3.0, 4.0)])
    write_midi(data / "d.mid", [(60, 0.5, 1.5)])
    write_midi(data / "e.mid", [(60, 0.5, 1.5)])
    entries = [
        entry("a", audio="a.wav", ref_midi="a.mid"),
        entry("b", style="jazz", quality="phone", audio="b.wav", ref_midi="b.mid"),
        entry("c", style="pop", quality="phone", audio="c.wav"),
        entry("d", ref_midi="d.mid"),
        entry("e", audio="gone.wav", ref_midi="e.mid"),
        entry("f", audio="f.wav", ref_midi="gone.mid"),
    ]
    path = tmp_path / "manifest.yaml"
    path.write_text(yaml.safe_dump({"version": 1, "data_dir": "data", "entries": entries}))
    return load_manifest(path)


def statuses(results):
    return {r.id: r.status for r in results}


def test_transcribe_all_statuses(manifest, tmp_path):
    results = transcribe_all(manifest, "fake", tmp_path / "c")
    assert statuses(results) == {
        "a": "transcribed", "b": "transcribed", "c": "transcribed",
        "d": "skipped", "e": "missing", "f": "transcribed",
    }  # fmt: skip
    assert FakeBackend.calls == 4


def test_transcribe_all_resumes_from_cache(manifest, tmp_path):
    transcribe_all(manifest, "fake", tmp_path / "c", only=["a", "b"])
    FakeBackend.calls = 0
    results = transcribe_all(manifest, "fake", tmp_path / "c")
    assert statuses(results)["a"] == "cached" and statuses(results)["b"] == "cached"
    assert statuses(results)["c"] == "transcribed"
    assert FakeBackend.calls == 2  # c und f


def test_transcribe_all_only_filter(manifest, tmp_path):
    results = transcribe_all(manifest, "fake", tmp_path / "c", only=["c"])
    assert [r.id for r in results] == ["c"]


def test_transcribe_all_continues_after_a_failed_piece(manifest, tmp_path):
    FakeBackend.fail_for = {1}
    results = transcribe_all(manifest, "fake", tmp_path / "c")
    assert results[0].status == "failed" and "Modellfehler" in results[0].message
    assert results[1].status == "transcribed"


def test_transcribe_all_reports_events(manifest, tmp_path):
    starts, dones = [], []
    transcribe_all(
        manifest, "fake", tmp_path / "c",
        on_start=lambda i, n, e: starts.append((i, n, e.id)),
        on_result=lambda i, n, r: dones.append((i, r.id)),
    )  # fmt: skip
    assert starts[0] == (1, 6, "a") and starts[-1] == (6, 6, "f")
    assert [d[0] for d in dones] == [1, 2, 3, 4, 5, 6]


def test_baseline_never_calls_the_backend(manifest, tmp_path):
    transcribe_all(manifest, "fake", tmp_path / "c")
    FakeBackend.calls = 0
    baseline(manifest, "fake", tmp_path / "c")
    assert FakeBackend.calls == 0


def test_baseline_values_and_statuses(manifest, tmp_path):
    transcribe_all(manifest, "fake", tmp_path / "c")
    rows = {r.id: r for r in baseline(manifest, "fake", tmp_path / "c")}
    assert rows["a"].status == "ok"
    assert (rows["a"].precision, rows["a"].recall, rows["a"].f1) == (1.0, 1.0, 1.0)
    assert (rows["a"].ref_notes, rows["a"].est_notes) == (2, 2)
    assert rows["b"].precision == 1.0
    assert rows["b"].recall == pytest.approx(2 / 3)
    assert rows["c"].status == "no_reference"
    assert rows["d"].status == "no_audio"
    assert rows["e"].status == "missing"
    assert rows["f"].status == "missing"


def test_baseline_not_transcribed_without_cache(manifest, tmp_path):
    rows = {r.id: r for r in baseline(manifest, "fake", tmp_path / "c")}
    assert rows["a"].status == "not_transcribed"
    assert rows["c"].status == "no_reference"
    assert FakeBackend.calls == 0
    assert not (tmp_path / "c").exists()


def test_baseline_cleanup_option_changes_estimate(manifest, tmp_path):
    transcribe_all(manifest, "fake", tmp_path / "c")
    cleaned = {r.id: r for r in baseline(manifest, "fake", tmp_path / "c")}
    raw = {r.id: r for r in baseline(manifest, "fake", tmp_path / "c", do_cleanup=False)}
    assert cleaned["a"].est_notes == 2 and raw["a"].est_notes == 3


def test_group_means_macro_average_over_pieces_with_f1(manifest, tmp_path):
    transcribe_all(manifest, "fake", tmp_path / "c")
    rows = baseline(manifest, "fake", tmp_path / "c")
    by_style = {g.name: g for g in group_means(rows, "style")}
    assert set(by_style) == {"classical", "jazz"}  # pop hat nur ein Stück ohne Referenz
    assert by_style["classical"].n == 1 and by_style["classical"].f1 == 1.0
    by_quality = {g.name: g for g in group_means(rows, "quality")}
    assert by_quality["studio"].n == 1
    assert by_quality["phone"].f1 == pytest.approx(rows[1].f1)
