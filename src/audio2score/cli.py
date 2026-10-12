import os
import sys
from pathlib import Path

import typer

from audio2score import __version__
from audio2score.audio.load import AudioLoadError
from audio2score.export.midi import write_midi
from audio2score.pipeline import score_file, transcribe_file
from audio2score.rhythm.base import RhythmError
from audio2score.rhythm.meter import parse_time_sig
from audio2score.transcribe import available_backends
from audio2score.transcribe.base import BackendUnavailableError, ModelDownloadError

app = typer.Typer(help="Klavieraufnahme rein, Noten raus.", no_args_is_help=True)

_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def note_name(midi: int) -> str:
    return f"{_NAMES[midi % 12]}{midi // 12 - 1}"


def _version(value: bool) -> None:
    if value:
        typer.echo(f"audio2score {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", callback=_version, is_eager=True, help="Version anzeigen."
    ),
) -> None:
    # Windows-Konsolen nutzen oft cp1252; Umlaute und Gedankenstriche sollen nicht zerfallen.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _check_backend(value: str) -> str:
    if value not in available_backends():
        raise typer.BadParameter(
            f"Unbekanntes Backend. Verfügbar: {', '.join(available_backends())}"
        )
    return value


def _fail(message: str) -> typer.Exit:
    typer.echo(f"Fehler: {message}", err=True)
    return typer.Exit(1)


def _format_duration(seconds: float) -> str:
    minutes, sec = divmod(seconds, 60)
    return f"{int(minutes)}:{sec:04.1f}"


@app.command()
def transcribe(
    audio: Path = typer.Argument(..., help="Audiodatei (wav, flac, mp3, m4a, ogg, ...)"),
    output: Path = typer.Option(..., "-o", "--output", help="Ziel-MIDI-Datei"),
    backend: str = typer.Option(
        "bytedance", "--backend", callback=_check_backend, help="bytedance | basic-pitch"
    ),
    cache_dir: Path | None = typer.Option(
        None, "--cache-dir", help="Cache-Ordner (sonst AUDIO2SCORE_CACHE, sonst ./cache)"
    ),
    no_cache: bool = typer.Option(False, "--no-cache", help="Cache weder lesen noch schreiben"),
    no_cleanup: bool = typer.Option(False, "--no-cleanup", help="Rohe Noten ohne Aufräumen"),
    checkpoint: Path | None = typer.Option(
        None, "--checkpoint", help="Modellgewichte (nur bytedance)"
    ),
) -> None:
    """Audio zu MIDI transkribieren."""
    typer.echo(f"Backend: {backend}")

    def on_download(done: int, total: int) -> None:
        shown = f"{done / 1e6:.0f} / {total / 1e6:.0f} MB" if total else f"{done / 1e6:.0f} MB"
        typer.echo(f"\rModellgewichte laden: {shown}", err=True, nl=False)
        if total and done >= total:
            typer.echo(err=True)

    try:
        result = transcribe_file(
            audio,
            backend=backend,
            cache_dir=cache_dir,
            use_cache=not no_cache,
            do_cleanup=not no_cleanup,
            checkpoint=checkpoint,
            on_download=on_download,
            on_transcribe=lambda: typer.echo("Transkribiere ..."),
        )
        nl = result.notelist
        write_midi(nl, output)
    except (AudioLoadError, BackendUnavailableError, ModelDownloadError) as e:
        raise _fail(str(e)) from e
    except OSError as e:
        raise _fail(f"{e.strerror or e}: {e.filename or ''}".strip()) from e

    typer.echo(f"Audiodauer: {_format_duration(nl.duration)}")
    typer.echo(f"Noten: {result.raw_count} roh, {len(nl.notes)} nach dem Aufräumen")
    if nl.notes:
        lo, hi = min(n.pitch for n in nl.notes), max(n.pitch for n in nl.notes)
        typer.echo(f"Tonumfang: {note_name(lo)}–{note_name(hi)}")
    else:
        typer.echo("Warnung: Es wurden keine Noten erkannt (leere MIDI-Datei).", err=True)
    typer.echo(f"Pedal-Events: {len(nl.pedals)}")
    typer.echo(f"Laufzeit: {result.elapsed:.1f} s" + (" (aus Cache)" if result.cache_hit else ""))
    typer.echo(f"MIDI: {output}")


def _check_time_sig(value: str | None) -> str | None:
    if value is not None:
        try:
            parse_time_sig(value)
        except ValueError as e:
            raise typer.BadParameter(str(e)) from e
    return value


_SOURCE_LABELS = {"detected": "erkannt", "given": "vorgegeben", "default": "Standard"}


@app.command()
def score(
    audio: Path = typer.Argument(..., help="Audiodatei (wav, flac, mp3, m4a, ogg, ...)"),
    output: Path = typer.Option(..., "-o", "--output", help="Zielordner (wird angelegt)"),
    time_sig: str | None = typer.Option(
        None,
        "--time-sig",
        callback=_check_time_sig,
        help="Taktart vorgeben: 2/4, 3/4, 4/4, 3/8, 6/8, 9/8, 12/8 (sonst automatisch)",
    ),
    backend: str = typer.Option(
        "bytedance", "--backend", callback=_check_backend, help="bytedance | basic-pitch"
    ),
    cache_dir: Path | None = typer.Option(
        None, "--cache-dir", help="Cache-Ordner (sonst AUDIO2SCORE_CACHE, sonst ./cache)"
    ),
    no_cache: bool = typer.Option(False, "--no-cache", help="Cache weder lesen noch schreiben"),
    checkpoint: Path | None = typer.Option(
        None, "--checkpoint", help="Modellgewichte (nur bytedance)"
    ),
) -> None:
    """Audio zu Partitur: MusicXML, quantisiertes MIDI und Beat-Datei."""
    typer.echo(f"Backend: {backend}")

    def on_download(done: int, total: int) -> None:
        shown = f"{done / 1e6:.0f} / {total / 1e6:.0f} MB" if total else f"{done / 1e6:.0f} MB"
        typer.echo(f"\rModellgewichte laden: {shown}", err=True, nl=False)
        if total and done >= total:
            typer.echo(err=True)

    try:
        result = score_file(
            audio,
            output,
            time_sig=parse_time_sig(time_sig) if time_sig else None,
            backend=backend,
            cache_dir=cache_dir,
            use_cache=not no_cache,
            checkpoint=checkpoint,
            on_download=on_download,
            on_transcribe=lambda: typer.echo("Transkribiere ..."),
            on_beats=lambda: typer.echo("Erkenne Beats ..."),
        )
    except (AudioLoadError, BackendUnavailableError, ModelDownloadError, RhythmError) as e:
        raise _fail(str(e)) from e
    except OSError as e:
        raise _fail(f"{e.strerror or e}: {e.filename or ''}".strip()) from e

    grid = result.grid
    meter = grid.meter
    typer.echo(f"Taktart: {meter.numerator}/{meter.denominator} ({_SOURCE_LABELS[meter.source]})")
    typer.echo(f"Tempo: {round(grid.tempo_bpm)} BPM")
    typer.echo(f"Takte: {result.bars}")
    typer.echo("Auftakt: " + ("ja" if grid.pickup_steps else "nein"))
    typer.echo(f"Noten: rechte Hand {result.right_notes}, linke Hand {result.left_notes}")
    for warning in result.warnings:
        typer.echo(f"Warnung: {warning}", err=True)
    cached = [
        label
        for label, hit in (("Noten", result.notes_cache_hit), ("Beats", result.beats_cache_hit))
        if hit
    ]
    typer.echo(
        f"Laufzeit: {result.elapsed:.1f} s"
        + (f" ({' und '.join(cached)} aus Cache)" if cached else "")
    )
    typer.echo(f"MusicXML: {result.musicxml}")
    typer.echo(f"MIDI: {result.midi}")
    typer.echo(f"Beats: {result.beats_json}")


# --- testset ---------------------------------------------------------------------------

testset_app = typer.Typer(
    help="Testset: laden, prüfen, transkribieren, Baseline.", no_args_is_help=True
)
app.add_typer(testset_app, name="testset")

_ManifestOpt = typer.Option(
    None, "--manifest", help="Manifest (sonst AUDIO2SCORE_TESTSET, sonst testset/manifest.yaml)"
)
_DataDirOpt = typer.Option(None, "--data-dir", help="Datenordner (überschreibt das Manifest)")
_CacheDirOpt = typer.Option(
    None, "--cache-dir", help="Cache-Ordner (sonst AUDIO2SCORE_CACHE, sonst ./cache)"
)
_BackendOpt = typer.Option("bytedance", "--backend", callback=_check_backend)
_OnlyOpt = typer.Option(None, "--only", help="Nur diese Eintrag-IDs (mehrfach angebbar)")


def _load_testset(manifest: Path | None, data_dir: Path | None, only: list[str] | None = None):
    from audio2score.testset.manifest import (
        DEFAULT_MANIFEST,
        ENV_VAR,
        ManifestError,
        load_manifest,
    )

    path = manifest or Path(os.environ.get(ENV_VAR) or DEFAULT_MANIFEST)
    try:
        loaded = load_manifest(path, data_dir)
    except ManifestError as e:
        for error in e.errors:
            typer.echo(f"FEHLER {error}", err=True)
        raise typer.Exit(1) from e
    unknown = sorted(set(only or []) - {e.id for e in loaded.entries})
    if unknown:
        raise _fail(f"Unbekannte Eintrag-ID(s): {', '.join(unknown)}")
    return loaded


@testset_app.command("check")
def testset_check(
    manifest: Path | None = _ManifestOpt, data_dir: Path | None = _DataDirOpt
) -> None:
    """Alle Einträge auf Vollständigkeit und Lesbarkeit prüfen."""
    from audio2score.testset.check import check_entry

    loaded = _load_testset(manifest, data_dir)
    counts = {"OK": 0, "WARN": 0, "FEHLER": 0}
    for entry in loaded.entries:
        issues = check_entry(entry)
        label = "FEHLER" if any(i.level == "error" for i in issues) else "WARN" if issues else "OK"
        counts[label] += 1
        typer.echo(f"{label:<6} {entry.id}")
        for issue in issues:
            typer.echo(f"         {issue.message}")
    typer.echo(
        f"{len(loaded.entries)} Einträge: {counts['OK']} OK, "
        f"{counts['WARN']} Warnung(en), {counts['FEHLER']} Fehler"
    )
    if counts["FEHLER"]:
        raise typer.Exit(1)


@testset_app.command("fetch")
def testset_fetch(
    manifest: Path | None = _ManifestOpt,
    data_dir: Path | None = _DataDirOpt,
    only: list[str] | None = _OnlyOpt,
    force: bool = typer.Option(False, "--force", help="Vorhandene Dateien neu laden"),
) -> None:
    """ASAP- und MAESTRO-Stücke laden (vorhandene Dateien werden übersprungen)."""
    from audio2score.testset.fetch import fetch_all

    loaded = _load_testset(manifest, data_dir, only)

    def on_progress(eid: str, done: int, total: int) -> None:
        typer.echo(f"\r  {eid}: {done / 1e6:.0f} / {total / 1e6:.0f} MB", err=True, nl=False)

    def on_result(result) -> None:
        typer.echo("\r" + " " * 70 + "\r", err=True, nl=False)
        label = {"ok": "geladen", "present": "vorhanden", "skipped": "übersprungen"}.get(
            result.status, "FEHLER"
        )
        typer.echo(f"{label:<13} {result.id}" + (f": {result.message}" if result.message else ""))

    results = fetch_all(loaded, only, force, on_progress, on_result)
    failed = sum(r.status == "failed" for r in results)
    typer.echo(f"{len(results)} Einträge, {failed} fehlgeschlagen")
    if failed:
        raise typer.Exit(1)


@testset_app.command("transcribe")
def testset_transcribe(
    manifest: Path | None = _ManifestOpt,
    data_dir: Path | None = _DataDirOpt,
    backend: str = _BackendOpt,
    cache_dir: Path | None = _CacheDirOpt,
    only: list[str] | None = _OnlyOpt,
) -> None:
    """Alle Audio-Stücke transkribieren; fertige Stücke kommen aus dem Cache."""
    from audio2score.testset.run import transcribe_all

    loaded = _load_testset(manifest, data_dir, only)

    def on_start(i: int, n: int, entry) -> None:
        typer.echo(f"[{i}/{n}] {entry.id} ... ", nl=False)

    def on_result(i: int, n: int, result) -> None:
        text = {
            "cached": "aus Cache",
            "transcribed": f"transkribiert in {result.seconds:.0f} s",
            "skipped": f"übersprungen ({result.message})",
            "missing": f"WARNUNG: {result.message}",
            "failed": f"FEHLER: {result.message}",
        }[result.status]
        typer.echo(text)

    def on_download(done: int, total: int) -> None:
        shown = f"{done / 1e6:.0f} / {total / 1e6:.0f} MB"
        typer.echo(f"\rModellgewichte laden: {shown}", err=True, nl=False)

    try:
        results = transcribe_all(
            loaded, backend, cache_dir, only, on_start, on_result,
            on_download=on_download,
        )  # fmt: skip
    except (BackendUnavailableError, ModelDownloadError) as e:
        typer.echo()
        raise _fail(str(e)) from e
    failed = sum(r.status == "failed" for r in results)
    if failed:
        raise typer.Exit(1)


def _baseline_cells(row) -> tuple[str, str, str, str]:
    if row.status == "ok":
        return (
            f"{row.precision:.3f}",
            f"{row.recall:.3f}",
            f"{row.f1:.3f}",
            f"{row.ref_notes}/{row.est_notes}",
        )
    note = {
        "no_reference": "keine Referenz",
        "no_audio": "kein Audio",
        "not_transcribed": "nicht transkribiert",
        "missing": row.message or "Datei fehlt",
    }[row.status]
    return (note, "", "", "")


@testset_app.command("baseline")
def testset_baseline(
    manifest: Path | None = _ManifestOpt,
    data_dir: Path | None = _DataDirOpt,
    backend: str = _BackendOpt,
    cache_dir: Path | None = _CacheDirOpt,
    no_cleanup: bool = typer.Option(False, "--no-cleanup", help="Rohe Noten ohne Aufräumen"),
) -> None:
    """Note-F1 pro Stück aus dem Cache (kein Modelllauf)."""
    from audio2score.testset.run import baseline, group_means

    loaded = _load_testset(manifest, data_dir)
    rows = baseline(loaded, backend, cache_dir, do_cleanup=not no_cleanup)

    width = max(len(r.id) for r in rows)

    def line(*cells: str) -> str:
        name, style, quality, p, r, f1, notes = cells
        return (
            f"{name:<{width}}  {style:<9}  {quality:<8}  {p:>6}  {r:>6}  {f1:>6}  {notes}".rstrip()
        )

    typer.echo(line("Stück", "Stil", "Qualität", "P", "R", "F1", "Noten (ref/est)"))
    for row in rows:
        p, r, f1, notes = _baseline_cells(row)
        if row.status != "ok":  # Hinweistext statt Zahlen
            typer.echo(line(row.id, row.style, row.quality, "-", "-", "-", p))
        else:
            typer.echo(line(row.id, row.style, row.quality, p, r, f1, notes))
    for key, title in (("style", "Stil"), ("quality", "Qualität")):
        typer.echo(f"\nMittelwert pro {title} (Makro über Stücke mit Referenz):")
        for g in group_means(rows, key):
            typer.echo(
                f"  {g.name:<10} n={g.n:<3} P {g.precision:.3f}  R {g.recall:.3f}  F1 {g.f1:.3f}"
            )
    missing = sum(r.status == "not_transcribed" for r in rows)
    if missing:
        typer.echo(
            f"\n{missing} Stück(e) nicht transkribiert - zuerst: audio2score testset transcribe",
            err=True,
        )
