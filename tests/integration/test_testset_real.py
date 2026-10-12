"""Echtes Testset (data/testset/, geladen mit `audio2score testset fetch`).

Ohne Daten wird übersprungen. `pytest -m slow` lädt das Modell, falls der Cache leer ist.
"""

from pathlib import Path

import pytest

from audio2score.testset.check import check_entry
from audio2score.testset.manifest import load_manifest
from audio2score.testset.run import baseline, transcribe_all

MANIFEST = Path(__file__).resolve().parents[2] / "testset" / "manifest.yaml"
MIN_F1 = 0.90  # fängt auch Zeitversatz zwischen Audio und Referenz ab
AUTO_SOURCES = ("asap", "maestro", "internet")


@pytest.fixture(scope="module")
def manifest():
    loaded = load_manifest(MANIFEST)
    if not loaded.data_dir.is_dir():
        pytest.skip(f"kein Testset in {loaded.data_dir} - laden mit: audio2score testset fetch")
    return loaded


@pytest.mark.slow
def test_check_has_no_errors_for_fetchable_and_internet_entries(manifest):
    problems = [
        f"{e.id}: {i.message}"
        for e in manifest.entries
        if e.source in AUTO_SOURCES
        for i in check_entry(e)
        if i.level == "error"
    ]
    assert not problems, "\n".join(problems)


@pytest.mark.slow
def test_note_f1_of_asap_and_maestro_pieces(manifest):
    cache_dir = (
        None  # Standard-Cache (./cache bzw. AUDIO2SCORE_CACHE), damit er wiederverwendet wird
    )
    only = [e.id for e in manifest.entries if e.source in ("asap", "maestro")]
    failed = [
        r for r in transcribe_all(manifest, "bytedance", cache_dir, only) if r.status == "failed"
    ]
    assert not failed, [f"{r.id}: {r.message}" for r in failed]
    rows = [r for r in baseline(manifest, "bytedance", cache_dir) if r.id in only]
    assert all(r.status == "ok" for r in rows), [(r.id, r.status) for r in rows if r.status != "ok"]
    low = [f"{r.id}: F1 {r.f1:.3f}" for r in rows if r.f1 < MIN_F1]
    assert not low, "\n".join(low)
