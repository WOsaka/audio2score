import sys
from pathlib import Path

import typer

from audio2score import __version__
from audio2score.audio.load import AudioLoadError
from audio2score.export.midi import write_midi
from audio2score.pipeline import transcribe_file
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
