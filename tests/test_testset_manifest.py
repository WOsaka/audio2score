from pathlib import Path

import pytest
import yaml

from audio2score.testset.manifest import ManifestError, load_manifest


def entry(**over):
    base = {
        "id": "a-piece",
        "style": "classical",
        "source": "own",
        "quality": "phone",
        "license": "privat",
        "origin": "eigene Aufnahme",
        "audio": "own/a.wav",
    }
    base.update(over)
    return {k: v for k, v in base.items() if v is not None}


@pytest.fixture
def write(tmp_path):
    def _write(entries, **top):
        doc = {"version": 1, "data_dir": "data", **top, "entries": entries}
        path = tmp_path / "manifest.yaml"
        path.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
        return path

    return _write


def errors_of(path, **kw):
    with pytest.raises(ManifestError) as exc:
        load_manifest(path, **kw)
    return exc.value.errors


def test_loads_entry_and_resolves_paths_against_data_dir(write, tmp_path):
    path = write(
        [
            entry(
                ref_midi="own/a.mid",
                ref_musicxml="own/a.musicxml",
                ref_annotations="own/a.txt",
                time_sig="3/4",
                tempo_hint=90,
                notes="Hinweis",
            )
        ]
    )
    m = load_manifest(path)
    e = m.entries[0]
    assert m.data_dir == (tmp_path / "data").resolve()
    assert e.audio == m.data_dir / "own" / "a.wav"
    assert e.ref_midi == m.data_dir / "own" / "a.mid"
    assert e.ref_musicxml == m.data_dir / "own" / "a.musicxml"
    assert e.ref_annotations == m.data_dir / "own" / "a.txt"
    assert (e.time_sig, e.tempo_hint, e.notes, e.fetch) == ("3/4", 90, "Hinweis", None)


def test_data_dir_option_overrides_manifest(write, tmp_path):
    other = tmp_path / "elsewhere"
    m = load_manifest(write([entry()]), data_dir=other)
    assert m.data_dir == other.resolve()


def test_entry_with_only_ref_midi_is_valid(write):
    m = load_manifest(write([entry(audio=None, ref_midi="asap/a.mid", source="asap")]))
    assert m.entries[0].audio is None


def test_fetch_block_is_parsed(write):
    fetch = {"maestro_audio": "2008/x.wav", "start": 1.0, "end": 9.5}
    m = load_manifest(write([entry(source="maestro", fetch=fetch)]))
    assert m.entries[0].fetch.maestro_audio == "2008/x.wav"
    assert (m.entries[0].fetch.start, m.entries[0].fetch.end) == (1.0, 9.5)


def test_collects_all_errors_with_entry_id(write):
    path = write(
        [
            entry(id="one", style="rock", source="web", quality=None),
            entry(id="two", license=None, origin=None, audio=None),
        ]
    )
    text = "\n".join(errors_of(path))
    assert "one" in text and "style" in text and "classical" in text  # erlaubte Werte genannt
    assert "source" in text and "quality" in text
    assert "two" in text and "license" in text and "origin" in text
    assert "audio" in text and "ref_midi" in text


def test_duplicate_ids(write):
    assert any("doppelt" in e and "a-piece" in e for e in errors_of(write([entry(), entry()])))


def test_id_must_be_kebab_case(write):
    assert any("kebab" in e for e in errors_of(write([entry(id="Bad_ID")])))


def test_unknown_field_is_an_error(write):
    assert any("auidio" in e for e in errors_of(write([entry(auidio="x.wav")])))


@pytest.mark.parametrize("bad", ["/abs/a.wav", "C:/abs/a.wav", "../out.wav", "own/../../out.wav"])
def test_paths_must_stay_inside_data_dir(write, bad):
    assert any("data_dir" in e for e in errors_of(write([entry(audio=bad)])))


@pytest.mark.parametrize(
    "fetch",
    [
        {},  # leer
        {"asap_folder": "Bach/Prelude/bwv_846"},  # Performance fehlt
        {"asap_performance": "Shi05M"},  # Ordner fehlt
        {"maestro_audio": "a.wav", "start": 5.0, "end": 5.0},
        {"maestro_audio": "a.wav", "start": 9.0, "end": 5.0},
        {"maestro_audio": "a.wav", "bogus": 1},
    ],
)
def test_incomplete_or_invalid_fetch(write, fetch):
    assert errors_of(write([entry(source="asap", fetch=fetch)]))


def test_missing_manifest_file(tmp_path):
    with pytest.raises(ManifestError) as exc:
        load_manifest(tmp_path / "nope.yaml")
    assert "nope.yaml" in exc.value.errors[0]


def test_broken_yaml(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text("entries: [unclosed", encoding="utf-8")
    assert errors_of(p)


def test_wrong_version_and_missing_entries(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text("version: 2\n", encoding="utf-8")
    text = "\n".join(errors_of(p))
    assert "version" in text and "entries" in text


def test_error_message_lists_every_error(write):
    path = write([entry(id="x", style="rock"), entry(id="y", quality="bad")])
    with pytest.raises(ManifestError) as exc:
        load_manifest(path)
    assert len(exc.value.errors) == 2
    assert str(exc.value).count("\n") >= 1
    assert isinstance(Path(path), Path)


def test_shipped_manifest_is_valid_and_has_the_required_composition():
    root = Path(__file__).resolve().parents[1] / "testset" / "manifest.yaml"
    entries = load_manifest(root).entries
    assert 12 <= len(entries) <= 15
    assert {e.style for e in entries} == {"classical", "pop", "jazz", "free"}
    assert "studio" in {e.quality for e in entries}
    assert {"phone", "internet"} & {e.quality for e in entries}
    assert sum(e.source == "asap" for e in entries) >= 6
    assert sum(e.source == "maestro" for e in entries) == 3
