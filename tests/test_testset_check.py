import subprocess
import zipfile

import pretty_midi
import pytest
import soundfile as sf

from audio2score.testset import check as check_mod
from audio2score.testset.check import check_entry
from audio2score.testset.manifest import Entry

SCORE = '<?xml version="1.0"?><score-partwise version="3.1"><part-list/></score-partwise>'


def make_entry(tmp_path, **paths):
    resolved = {k: (tmp_path / v if v else None) for k, v in paths.items()}
    return Entry(
        id="e",
        style="classical",
        source="own",
        quality="phone",
        license="l",
        origin="o",
        **resolved,
    )


def levels(issues):
    return [i.level for i in issues]


@pytest.fixture
def midi_file(tmp_path):
    midi = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(program=0)
    inst.notes.append(pretty_midi.Note(80, 60, 0.0, 1.0))
    midi.instruments.append(inst)
    path = tmp_path / "ok.mid"
    midi.write(str(path))
    return path


def test_complete_entry_has_no_issues(tmp_path, make_wav, midi_file):
    make_wav("a.wav")
    (tmp_path / "s.musicxml").write_text(SCORE, encoding="utf-8")
    (tmp_path / "s.txt").write_text("0.5\t0.5\tdb,4/4\n1.0\t1.0\tb\n", encoding="utf-8")
    entry = make_entry(
        tmp_path,
        audio="a.wav",
        ref_midi="ok.mid",
        ref_musicxml="s.musicxml",
        ref_annotations="s.txt",
    )
    assert check_entry(entry) == []


def test_missing_optional_references_are_fine(tmp_path, make_wav):
    make_wav("a.wav")
    assert check_entry(make_entry(tmp_path, audio="a.wav")) == []


@pytest.mark.parametrize("field", ["audio", "ref_midi", "ref_musicxml", "ref_annotations"])
def test_listed_but_missing_file_is_an_error(tmp_path, field):
    issues = check_entry(make_entry(tmp_path, **{field: "nope.bin"}))
    assert levels(issues) == ["error"]
    assert "nope.bin" in issues[0].message


def test_text_as_wav_is_an_error(tmp_path):
    (tmp_path / "a.wav").write_text("das ist kein audio", encoding="utf-8")
    issues = check_entry(make_entry(tmp_path, audio="a.wav"))
    assert levels(issues) == ["error"] and "a.wav" in issues[0].message


def test_truncated_wav_is_an_error(tmp_path, make_wav):
    path = make_wav("a.wav", dur=2.0)
    data = path.read_bytes()
    path.write_bytes(data[: len(data) // 2])
    issues = check_entry(make_entry(tmp_path, audio="a.wav"))
    assert levels(issues) == ["error"]


def test_unreadable_by_soundfile_falls_back_to_ffmpeg(tmp_path, make_wav, monkeypatch):
    make_wav("a.wav")

    def no_sf(*a, **k):
        raise sf.LibsndfileError(1)

    monkeypatch.setattr(check_mod.sf, "info", no_sf)
    assert check_entry(make_entry(tmp_path, audio="a.wav")) == []  # ffmpeg liest die WAV


def test_ffmpeg_missing_makes_unreadable_audio_an_error(tmp_path, monkeypatch):
    (tmp_path / "a.m4a").write_bytes(b"xx")
    monkeypatch.setattr(check_mod, "find_ffmpeg", lambda: None)
    issues = check_entry(make_entry(tmp_path, audio="a.m4a"))
    assert levels(issues) == ["error"] and "ffmpeg" in issues[0].message


def test_ffmpeg_failure_is_an_error(tmp_path, monkeypatch):
    (tmp_path / "a.m4a").write_bytes(b"xx")
    monkeypatch.setattr(check_mod, "find_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(
        check_mod.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 1, b"", b"Invalid data\n"),
    )
    issues = check_entry(make_entry(tmp_path, audio="a.m4a"))
    assert levels(issues) == ["error"] and "Invalid data" in issues[0].message


def test_text_as_midi_is_an_error(tmp_path):
    (tmp_path / "a.mid").write_text("kein midi", encoding="utf-8")
    assert levels(check_entry(make_entry(tmp_path, ref_midi="a.mid"))) == ["error"]


def test_midi_without_notes_is_a_warning(tmp_path):
    pretty_midi.PrettyMIDI().write(str(tmp_path / "empty.mid"))
    assert levels(check_entry(make_entry(tmp_path, ref_midi="empty.mid"))) == ["warn"]


def test_broken_musicxml_is_an_error(tmp_path):
    (tmp_path / "s.musicxml").write_text("<score-partwise><part>", encoding="utf-8")
    assert levels(check_entry(make_entry(tmp_path, ref_musicxml="s.musicxml"))) == ["error"]


def test_musicxml_with_wrong_root_is_an_error(tmp_path):
    (tmp_path / "s.musicxml").write_text("<html/>", encoding="utf-8")
    issues = check_entry(make_entry(tmp_path, ref_musicxml="s.musicxml"))
    assert levels(issues) == ["error"] and "score-partwise" in issues[0].message


def test_mxl_zip_is_read(tmp_path):
    with zipfile.ZipFile(tmp_path / "s.mxl", "w") as z:
        z.writestr("META-INF/container.xml", "<container/>")
        z.writestr("score.xml", SCORE)
    assert check_entry(make_entry(tmp_path, ref_musicxml="s.mxl")) == []


def test_mxl_without_score_is_an_error(tmp_path):
    with zipfile.ZipFile(tmp_path / "s.mxl", "w") as z:
        z.writestr("readme.txt", "hi")
    assert levels(check_entry(make_entry(tmp_path, ref_musicxml="s.mxl"))) == ["error"]


@pytest.mark.parametrize("content", ["", "nur text\n", "abc\t1.0\tx\n"])
def test_bad_annotations_are_an_error(tmp_path, content):
    (tmp_path / "s.txt").write_text(content, encoding="utf-8")
    assert levels(check_entry(make_entry(tmp_path, ref_annotations="s.txt"))) == ["error"]


def test_valid_mp3_is_not_reported_as_truncated(tmp_path, make_wav):
    # MP3: libsndfile schätzt die Frame-Zahl, das Ende darf nicht als Abschneiden gelten
    ffmpeg = check_mod.find_ffmpeg()
    wav = make_wav("a.wav", dur=2.0)
    subprocess.run(
        [ffmpeg, "-v", "error", "-y", "-i", str(wav), "-write_xing", "0", str(tmp_path / "a.mp3")],
        check=True,
    )
    assert check_entry(make_entry(tmp_path, audio="a.mp3")) == []
