import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from audio2score import cache
from audio2score.audio.load import SAMPLE_RATE, AudioLoadError, load_audio
from audio2score.cleanup.notes import cleanup
from audio2score.export.beats import write_beats_json
from audio2score.export.quantized_midi import write_quantized_midi
from audio2score.model import NoteList
from audio2score.rhythm import get_beat_tracker
from audio2score.rhythm.base import Beats, BeatTracker, RhythmError
from audio2score.rhythm.beat_this import SAMPLE_RATE as BEAT_SAMPLE_RATE
from audio2score.rhythm.meter import Grid, build_grid
from audio2score.rhythm.quantize import quantize
from audio2score.score.hands import split_hands
from audio2score.score.voices import single_voice
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


def cached_beats(
    audio_path: Path, cache_dir: Path | None = None, tracker: BeatTracker | None = None
) -> Beats | None:
    """Nur den Beat-Cache lesen: kein Audio laden, kein Modell laden. None bei einem Fehltreffer."""
    audio_path = Path(audio_path)
    if not audio_path.is_file():
        raise AudioLoadError(f"Datei nicht gefunden: {audio_path}")
    tracker = tracker or get_beat_tracker()
    key = cache.beat_cache_key(audio_path, tracker)
    return cache.load_beats(cache.resolve_cache_dir(cache_dir), key)


def detect_beats(
    audio_path: Path,
    cache_dir: Path | None = None,
    use_cache: bool = True,
    tracker: BeatTracker | None = None,
    on_beats: Callable[[], None] | None = None,
) -> tuple[Beats, bool]:
    """Beat-Cache oder Tracker. Gibt (Beats, Cache-Treffer) zurück.

    Ohne `use_cache` wird der Cache weder gelesen noch geschrieben.
    """
    audio_path = Path(audio_path)
    if not audio_path.is_file():
        raise AudioLoadError(f"Datei nicht gefunden: {audio_path}")
    tracker = tracker or get_beat_tracker()
    directory = cache.resolve_cache_dir(cache_dir)
    key = cache.beat_cache_key(audio_path, tracker) if use_cache else None
    beats = cache.load_beats(directory, key) if use_cache else None
    if beats is not None:
        return beats, True
    audio = load_audio(audio_path, BEAT_SAMPLE_RATE)
    if on_beats:
        on_beats()
    beats = tracker.track(audio, BEAT_SAMPLE_RATE)
    if use_cache:
        cache.save_beats(directory, key, beats)
    return beats, False


@dataclass
class ScoreResult:
    musicxml: Path
    midi: Path
    beats_json: Path
    grid: Grid
    bars: int
    right_notes: int
    left_notes: int
    warnings: list[str]
    notes_cache_hit: bool
    beats_cache_hit: bool
    elapsed: float


def score_file(
    audio_path: Path,
    out_dir: Path,
    time_sig: tuple[int, int] | None = None,
    backend: str = "bytedance",
    cache_dir: Path | None = None,
    use_cache: bool = True,
    checkpoint: Path | None = None,
    on_download: Callable[[int, int], None] | None = None,
    on_transcribe: Callable[[], None] | None = None,
    on_beats: Callable[[], None] | None = None,
    tracker: BeatTracker | None = None,
) -> ScoreResult:
    """Teil A (Cache oder Transkription, Beats) → Teil B (Partitur) → drei Dateien.

    Geschrieben wird erst, wenn alles berechnet ist: Bei einem Fehler entstehen keine Dateien.
    """
    # music21 braucht ~0,5 s beim Import; die anderen Befehle sollen davon nichts merken
    from audio2score.export.musicxml import write_musicxml
    from audio2score.score.build import build_score

    start = time.perf_counter()
    audio_path = Path(audio_path)
    transcription = transcribe_file(
        audio_path, backend, cache_dir, use_cache, True, checkpoint, on_download, on_transcribe
    )
    notes = transcription.notelist.notes
    if not notes:
        raise RhythmError("Keine Noten erkannt")
    beats, beats_hit = detect_beats(audio_path, cache_dir, use_cache, tracker, on_beats)

    grid = build_grid(beats, notes, time_sig)
    right, left = split_hands(quantize(notes, grid))
    right, left = single_voice(right), single_voice(left)
    score = build_score(right, left, grid, audio_path.stem)

    out_dir = Path(out_dir)
    musicxml = out_dir / f"{audio_path.stem}.musicxml"
    midi = out_dir / f"{audio_path.stem}.quantized.mid"
    beats_json = out_dir / f"{audio_path.stem}.beats.json"
    write_musicxml(score, musicxml)
    write_quantized_midi(right, left, grid, midi)
    write_beats_json(grid, beats, beats_json, audio_path.name)
    return ScoreResult(
        musicxml,
        midi,
        beats_json,
        grid,
        grid.bars,
        len(right),
        len(left),
        list(grid.warnings),
        transcription.cache_hit,
        beats_hit,
        time.perf_counter() - start,
    )
