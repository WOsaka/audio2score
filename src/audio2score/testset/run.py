"""Testset-Läufe: Teil A in den Cache schreiben und die Baseline daraus berechnen."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from audio2score.eval.notes import note_prf, read_midi_notes
from audio2score.pipeline import cached_transcription, transcribe_file
from audio2score.testset.manifest import Entry, Manifest
from audio2score.transcribe.base import BackendUnavailableError, ModelDownloadError


@dataclass
class RunResult:
    id: str
    status: Literal["cached", "transcribed", "skipped", "missing", "failed"]
    seconds: float = 0.0
    message: str = ""


def _selected(manifest: Manifest, only: list[str] | None) -> list[Entry]:
    return [e for e in manifest.entries if not only or e.id in only]


def transcribe_all(
    manifest: Manifest,
    backend: str,
    cache_dir: Path | None,
    only: list[str] | None = None,
    on_start: Callable[[int, int, Entry], None] | None = None,
    on_result: Callable[[int, int, RunResult], None] | None = None,
    on_download: Callable[[int, int], None] | None = None,
) -> list[RunResult]:
    """Transkribiert alle Audio-Einträge, die noch nicht im Cache liegen."""
    entries = _selected(manifest, only)
    results = []
    for i, entry in enumerate(entries, 1):
        if on_start:
            on_start(i, len(entries), entry)
        start = time.perf_counter()
        if entry.audio is None:
            result = RunResult(entry.id, "skipped", message="kein Audio (nur Referenz)")
        elif not entry.audio.is_file():
            result = RunResult(entry.id, "missing", message=f"Datei fehlt: {entry.audio}")
        else:
            try:
                hit = cached_transcription(entry.audio, backend, cache_dir)
                if hit is None:
                    transcribe_file(entry.audio, backend, cache_dir, on_download=on_download)
                status = "cached" if hit else "transcribed"
                result = RunResult(entry.id, status, time.perf_counter() - start)
            except (BackendUnavailableError, ModelDownloadError):
                raise  # betrifft alle Stücke, weiterzumachen hilft nicht
            except Exception as e:  # pro Stück melden und weitermachen
                result = RunResult(entry.id, "failed", message=f"{type(e).__name__}: {e}")
        results.append(result)
        if on_result:
            on_result(i, len(entries), result)
    return results


@dataclass
class BaselineRow:
    id: str
    style: str
    quality: str
    status: Literal["ok", "no_reference", "no_audio", "missing", "not_transcribed"]
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    ref_notes: int = 0
    est_notes: int = 0
    message: str = ""


def _baseline_row(entry: Entry, backend: str, cache_dir: Path | None, do_cleanup: bool):
    def row(status, **kw) -> BaselineRow:
        return BaselineRow(entry.id, entry.style, entry.quality, status, **kw)

    if entry.ref_midi is None:
        return row("no_reference")
    if entry.audio is None:
        return row("no_audio")
    for path in (entry.audio, entry.ref_midi):
        if not path.is_file():
            return row("missing", message=f"Datei fehlt: {path}")
    result = cached_transcription(entry.audio, backend, cache_dir, do_cleanup)
    if result is None:
        return row("not_transcribed")
    reference = read_midi_notes(entry.ref_midi)
    estimate = result.notelist.notes
    p, r, f1 = note_prf(reference, estimate)
    return row(
        "ok", precision=p, recall=r, f1=f1, ref_notes=len(reference), est_notes=len(estimate)
    )


def baseline(
    manifest: Manifest, backend: str, cache_dir: Path | None, do_cleanup: bool = True
) -> list[BaselineRow]:
    """Note-F1 pro Stück, nur aus dem Cache. Lädt nie ein Modell."""
    return [_baseline_row(e, backend, cache_dir, do_cleanup) for e in manifest.entries]


@dataclass
class GroupMean:
    name: str
    n: int
    precision: float
    recall: float
    f1: float


def group_means(rows: list[BaselineRow], key: Literal["style", "quality"]) -> list[GroupMean]:
    """Makro-Mittel über die Stücke mit F1, gruppiert nach Stil oder Qualität."""
    groups: dict[str, list[BaselineRow]] = {}
    for row in rows:
        if row.status == "ok":
            groups.setdefault(getattr(row, key), []).append(row)
    return [
        GroupMean(
            name,
            len(items),
            sum(r.precision for r in items) / len(items),
            sum(r.recall for r in items) / len(items),
            sum(r.f1 for r in items) / len(items),
        )
        for name, items in sorted(groups.items())
    ]
