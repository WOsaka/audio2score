import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from audio2score import cache
from audio2score.audio.load import SAMPLE_RATE, AudioLoadError, load_audio
from audio2score.cleanup.notes import cleanup
from audio2score.model import NoteList
from audio2score.transcribe import get_transcriber


@dataclass
class TranscriptionResult:
    notelist: NoteList  # nach Cleanup (falls aktiv)
    raw_count: int
    cache_hit: bool
    elapsed: float


def cached_transcription(
    audio_path: Path,
    backend: str = "bytedance",
    cache_dir: Path | None = None,
    do_cleanup: bool = True,
) -> TranscriptionResult | None:
    """Nur den Cache lesen: kein Audio laden, kein Modell laden. None bei einem Fehltreffer."""
    start = time.perf_counter()
    audio_path = Path(audio_path)
    if not audio_path.is_file():
        raise AudioLoadError(f"Datei nicht gefunden: {audio_path}")
    transcriber = get_transcriber(backend)  # lädt das Modell erst bei transcribe()
    key = cache.cache_key(audio_path, transcriber)
    raw = cache.load(cache.resolve_cache_dir(cache_dir), key)
    if raw is None:
        return None
    return _result(raw, do_cleanup, True, start)


def _result(raw: NoteList, do_cleanup: bool, cache_hit: bool, start: float) -> TranscriptionResult:
    notelist = cleanup(raw) if do_cleanup else raw
    return TranscriptionResult(notelist, len(raw.notes), cache_hit, time.perf_counter() - start)


def transcribe_file(
    audio_path: Path,
    backend: str = "bytedance",
    cache_dir: Path | None = None,
    use_cache: bool = True,
    do_cleanup: bool = True,
    checkpoint: Path | None = None,
    on_download: Callable[[int, int], None] | None = None,
    on_transcribe: Callable[[], None] | None = None,
) -> TranscriptionResult:
    """Audio laden → Cache oder Backend → Aufräumen. Der Cache hält die rohe NoteList.

    Bei einem Cache-Treffer wird das Audio nicht geladen (Schlüssel = Datei-Hash).
    Ohne `use_cache` wird der Cache weder gelesen noch geschrieben.
    """
    start = time.perf_counter()
    audio_path = Path(audio_path)
    if not audio_path.is_file():
        raise AudioLoadError(f"Datei nicht gefunden: {audio_path}")

    options = {}
    if backend == "bytedance":
        options = {"checkpoint": checkpoint, "progress": on_download}
    transcriber = get_transcriber(backend, **options)

    directory = cache.resolve_cache_dir(cache_dir)
    key = cache.cache_key(audio_path, transcriber) if use_cache else None
    raw = cache.load(directory, key) if use_cache else None
    cache_hit = raw is not None
    if raw is None:
        audio = load_audio(audio_path, SAMPLE_RATE)
        if on_transcribe:
            on_transcribe()
        raw = transcriber.transcribe(audio, SAMPLE_RATE)
        if use_cache:
            cache.save(directory, key, raw)

    return _result(raw, do_cleanup, cache_hit, start)
