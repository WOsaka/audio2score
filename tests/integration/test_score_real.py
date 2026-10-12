"""Echtes `beat_this` und echtes Testset (data/testset/, geladen mit `audio2score testset fetch`).

Ohne Daten wird übersprungen. `pytest -m slow` lädt Modelle, falls Caches leer sind.
"""

import statistics
from pathlib import Path

import pytest

from audio2score.audio.load import load_audio
from audio2score.rhythm.beat_this import SAMPLE_RATE, BeatThisTracker
from audio2score.testset.manifest import load_manifest
from audio2score.testset.run import score_all, transcribe_all

MANIFEST = Path(__file__).resolve().parents[2] / "testset" / "manifest.yaml"


@pytest.fixture(scope="module")
def manifest():
    loaded = load_manifest(MANIFEST)
    if not loaded.data_dir.is_dir():
        pytest.skip(f"kein Testset in {loaded.data_dir} - laden mit: audio2score testset fetch")
    return loaded


@pytest.mark.slow
def test_beat_this_finds_plausible_beats_in_a_real_recording(manifest):
    entry = next(e for e in manifest.entries if e.id == "asap-bach-fugue-bwv856")
    if entry.audio is None or not entry.audio.is_file():
        pytest.skip("Audio der Fuge fehlt")
    beats = BeatThisTracker().track(load_audio(entry.audio, SAMPLE_RATE), SAMPLE_RATE)
    gaps = [b - a for a, b in zip(beats.times, beats.times[1:], strict=False)]
    assert 0.2 < statistics.median(gaps) < 0.4  # Achtel bei ~100 BPM (Referenz: 0,3 s)
    assert 180 < len(beats.times) < 250  # Referenz: 215
    assert set(beats.downbeats) <= set(beats.times)
    assert 60 < len(beats.downbeats) < 85  # Referenz: 72 Takte


@pytest.mark.slow
def test_every_testset_piece_yields_a_readable_musicxml(manifest, tmp_path):
    cache_dir = None  # Standard-Cache, damit Noten und Beats wiederverwendet werden
    audio_ids = [e.id for e in manifest.entries if e.audio is not None]
    failed = [
        r
        for r in transcribe_all(manifest, "bytedance", cache_dir, audio_ids)
        if r.status == "failed"
    ]
    assert not failed, [f"{r.id}: {r.message}" for r in failed]
    rows = score_all(manifest, "bytedance", cache_dir, tmp_path, audio_ids)
    bad = [(r.id, r.status, r.message) for r in rows if r.status != "ok"]
    assert not bad, bad
    assert len(rows) == len(audio_ids)
