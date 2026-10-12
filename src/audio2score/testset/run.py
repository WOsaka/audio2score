"""Testset-Läufe: Teil A in den Cache schreiben und die Baseline daraus berechnen."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from audio2score.eval.notes import note_prf, read_midi_notes
from audio2score.pipeline import cached_transcription, score_file, transcribe_file
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


@dataclass
class ScoreRow:
    id: str
    status: Literal["ok", "skipped", "not_transcribed", "missing", "failed"]
    time_sig: str = ""  # erkannt (oder Standard)
    expected_time_sig: str | None = None  # aus dem Manifest, nur zum Vergleich
    bars: int = 0
    expected_bars: int | None = None  # Downbeats der ASAP-Annotation
    pickup: bool = False
    seconds: float = 0.0
    message: str = ""


def count_downbeats(path: Path) -> int:
    """Anzahl der Downbeats (`db`) in einer ASAP-Annotationsdatei."""
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) >= 3 and fields[2].split(",")[0].strip() == "db":
            count += 1
    return count


def _reread(path: Path) -> None:
    """Liest das MusicXML mit music21 wieder ein; wirft, wenn es nicht lesbar ist."""
    from music21 import converter

    parts = converter.parse(path).parts
    if len(parts) != 2:
        raise ValueError(f"MusicXML hat {len(parts)} statt 2 Systeme")


def score_all(
    manifest: Manifest,
    backend: str,
    cache_dir: Path | None,
    out_dir: Path,
    only: list[str] | None = None,
    on_start: Callable[[int, int, Entry], None] | None = None,
    on_result: Callable[[int, int, ScoreRow], None] | None = None,
) -> list[ScoreRow]:
    """Partitur für alle Audio-Stücke; Noten nur aus dem Cache, Beats werden bei Bedarf gerechnet.

    Die Taktart des Manifests wird nicht als Hinweis benutzt, nur verglichen.
    """
    entries = _selected(manifest, only)
    rows = []
    for i, entry in enumerate(entries, 1):
        if on_start:
            on_start(i, len(entries), entry)
        start = time.perf_counter()
        base = {"expected_time_sig": entry.time_sig}
        if entry.ref_annotations is not None and entry.ref_annotations.is_file():
            base["expected_bars"] = count_downbeats(entry.ref_annotations)
        if entry.audio is None:
            row = ScoreRow(entry.id, "skipped", message="kein Audio (nur Referenz)", **base)
        elif not entry.audio.is_file():
            row = ScoreRow(entry.id, "missing", message=f"Datei fehlt: {entry.audio}", **base)
        elif cached_transcription(entry.audio, backend, cache_dir) is None:
            row = ScoreRow(entry.id, "not_transcribed", message="nicht transkribiert", **base)
        else:
            try:
                result = score_file(entry.audio, out_dir, backend=backend, cache_dir=cache_dir)
                _reread(result.musicxml)
                meter = result.grid.meter
                row = ScoreRow(
                    entry.id,
                    "ok",
                    time_sig=f"{meter.numerator}/{meter.denominator}",
                    bars=result.bars,
                    pickup=result.grid.pickup_steps > 0,
                    seconds=time.perf_counter() - start,
                    message="; ".join(result.warnings),
                    **base,
                )
            except (BackendUnavailableError, ModelDownloadError):
                raise  # betrifft alle Stücke, weiterzumachen hilft nicht
            except Exception as e:  # pro Stück melden und weitermachen
                row = ScoreRow(entry.id, "failed", message=f"{type(e).__name__}: {e}", **base)
        rows.append(row)
        if on_result:
            on_result(i, len(entries), row)
    return rows
