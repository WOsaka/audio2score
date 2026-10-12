import json
import logging

import pytest

from audio2score import cache
from audio2score.model import Note, NoteList


class FakeTranscriber:
    def __init__(self, name="fake", version="1"):
        self.name = name
        self.version = version


def make_nl():
    return NoteList([Note(60, 0.0, 1.0, 80)], [], 1.0, "fake", "1")


def test_dir_option_beats_env_beats_default(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIO2SCORE_CACHE", str(tmp_path / "env"))
    assert cache.resolve_cache_dir(tmp_path / "opt") == tmp_path / "opt"
    assert cache.resolve_cache_dir(None) == tmp_path / "env"
    monkeypatch.delenv("AUDIO2SCORE_CACHE")
    assert cache.resolve_cache_dir(None).name == "cache"


def test_key_depends_on_content_backend_and_version(tmp_path):
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    a.write_bytes(b"one")
    b.write_bytes(b"two")
    same = tmp_path / "same.wav"
    same.write_bytes(b"one")
    t = FakeTranscriber()
    assert cache.cache_key(a, t) == cache.cache_key(same, t)  # Inhalt, nicht Name
    assert cache.cache_key(a, t) != cache.cache_key(b, t)
    assert cache.cache_key(a, t) != cache.cache_key(a, FakeTranscriber("other"))
    assert cache.cache_key(a, t) != cache.cache_key(a, FakeTranscriber(version="2"))


def test_key_is_filename_safe(tmp_path):
    a = tmp_path / "a.wav"
    a.write_bytes(b"x")
    key = cache.cache_key(a, FakeTranscriber("bytedance", "0.0.6+note_F1=0.9677/x"))
    assert all(c.isalnum() or c in "-_.+=" for c in key)


def test_save_and_load_roundtrip(tmp_path):
    cache.save(tmp_path / "c", "k", make_nl())
    assert cache.load(tmp_path / "c", "k") == make_nl()


def test_load_missing_returns_none(tmp_path):
    assert cache.load(tmp_path, "nope") is None


def test_corrupt_entry_returns_none_with_warning_and_is_overwritable(tmp_path, caplog):
    cache.save(tmp_path, "k", make_nl())
    (tmp_path / "k.json").write_text("{kaputt", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert cache.load(tmp_path, "k") is None
    assert "k" in caplog.text
    cache.save(tmp_path, "k", make_nl())
    assert cache.load(tmp_path, "k") == make_nl()


def test_old_schema_returns_none(tmp_path, caplog):
    (tmp_path / "k.json").write_text(
        json.dumps({"schema": 0, "notelist": make_nl().to_dict()}), encoding="utf-8"
    )
    with caplog.at_level(logging.WARNING):
        assert cache.load(tmp_path, "k") is None


@pytest.mark.parametrize("payload", ['{"schema": 1}', '{"schema": 1, "notelist": {"notes": 5}}'])
def test_structurally_invalid_entry_returns_none(tmp_path, payload):
    (tmp_path / "k.json").write_text(payload, encoding="utf-8")
    assert cache.load(tmp_path, "k") is None
