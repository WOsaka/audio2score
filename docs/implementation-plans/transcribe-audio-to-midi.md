---
title: "Implementation Plan: Transcribe Audio to MIDI"
feature_spec: docs/features/transcribe-audio-to-midi.md
status: implemented   # pending-approval | approved | implemented
created: 2026-10-11
updated: 2026-10-12
---

# Implementation Plan: Transcribe Audio to MIDI

## Summary
Greenfield-Python-Paket `audio2score` (src-Layout, Python 3.12, hatchling) mit Typer-CLI. Die Pipeline lädt Audio selbst (soundfile, ffmpeg als Fallback), übergibt ein Mono-16-kHz-Array an ein austauschbares Backend (`Transcriber`-Protokoll), speichert die **rohe** `NoteList` als JSON im Cache, wendet danach optional das Aufräumen an und exportiert MIDI über `pretty_midi`. Weil der Cache die Rohdaten hält, funktionieren `--no-cleanup` und spätere Änderungen an den Aufräumregeln ohne erneuten Modelllauf.

### Ergebnisse der Recherche, die das Design bestimmen
1. **`piano_transcription_inference` 0.0.6** (MIT) lädt die Gewichte (~165 MB, Zenodo) per `os.system("wget …")`. Unter Windows schlägt das fehl, weil `wget` fehlt. Außerdem ist `device` standardmäßig `cuda`. → Eigener Download (urllib, Fortschritt, atomares Umbenennen), dann `PianoTranscription(device="cpu", checkpoint_path=…)`. `transcribe(audio, None)` schreibt keine Datei und liefert `est_note_events` (`onset_time`, `offset_time`, `midi_note`, `velocity`) und `est_pedal_events` (`onset_time`, `offset_time`). Die Note-Offsets sind **Tasten-Offsets** (nicht pedal-verlängert), wie von der Roadmap gefordert. `torch` wird von dem Paket nicht deklariert und muss selbst angegeben werden. Unter Windows ist das Standard-Wheel von PyPI bereits CPU-only.
2. **`basic-pitch` 0.4.0** verlangt unter Windows mit Python ≥ 3.11 `tensorflow<2.15.1`, und dafür gibt es keine cp312-Wheels. Mit Python 3.12 ist es also **nicht regulär installierbar**. Das Paket enthält aber das ONNX-Modell (`saved_models/icassp_2022/nmp.onnx`) und wählt automatisch ONNX, wenn nur `onnxruntime` vorhanden ist. → Das Extra `basic-pitch` installiert `onnxruntime` und die übrigen Laufzeit-Abhängigkeiten. `basic-pitch` selbst wird in einem dokumentierten zweiten Schritt mit `pip install --no-deps basic-pitch==0.4.0` installiert. Das entspricht der Spec-Entscheidung „dokumentieren statt auf 3.11 wechseln“.
3. **Lokale Umgebung**: Python 3.12.10 vorhanden (`py -3.12`), **ffmpeg fehlt**, MuseScore fehlt (für dieses Feature irrelevant). → Abhängigkeit `imageio-ffmpeg` (liefert eine ffmpeg-Binärdatei als Wheel). Reihenfolge: ffmpeg im `PATH`, sonst die `imageio-ffmpeg`-Binärdatei. Die in der Spec geforderte Fehlermeldung bei fehlendem ffmpeg bleibt für den Fall, dass beides fehlt.

## Files to Create
| File | Purpose |
|------|---------|
| `pyproject.toml` | Paket-Metadaten, Abhängigkeiten, Extras `basic-pitch`/`dev`, Entry Point `audio2score`, Konfiguration für ruff + pytest |
| `src/audio2score/__init__.py` | `__version__` |
| `src/audio2score/model.py` | `Note`, `PedalEvent`, `NoteList` + JSON-Serialisierung |
| `src/audio2score/audio/__init__.py` | – |
| `src/audio2score/audio/load.py` | `load_audio()`: Decodieren, Mono, Resampling, Normalisierung; ffmpeg-Ermittlung |
| `src/audio2score/transcribe/__init__.py` | Registry `get_transcriber()`, `available_backends()` |
| `src/audio2score/transcribe/base.py` | `Transcriber`-Protokoll, Fehlerklassen |
| `src/audio2score/transcribe/bytedance.py` | ByteDance-Backend inkl. Checkpoint-Auflösung und -Download |
| `src/audio2score/transcribe/basic_pitch.py` | Basic-Pitch-Backend (ONNX), lazy Import |
| `src/audio2score/cache.py` | Cache-Ort, Schlüssel, Laden/Speichern |
| `src/audio2score/cleanup/__init__.py` | – |
| `src/audio2score/cleanup/notes.py` | `CleanupConfig`, `cleanup()` |
| `src/audio2score/export/__init__.py` | – |
| `src/audio2score/export/midi.py` | `write_midi()` inkl. CC64 |
| `src/audio2score/pipeline.py` | `transcribe_file()`: Orchestrierung (laden → Cache/Backend → Aufräumen) |
| `src/audio2score/cli.py` | Typer-App, Befehl `transcribe` |
| `tests/conftest.py` | Fixtures: synthetisches Audio, Beispiel-`NoteList`, Fake-Backend |
| `tests/test_model.py` | JSON-Roundtrip, Validierung |
| `tests/test_audio_load.py` | Formate, Stereo/Samplerate, Fehlerfälle |
| `tests/test_cache.py` | Ortsauflösung, Schlüssel, beschädigte/alte Einträge |
| `tests/test_cleanup.py` | Mindestdauer, leise Noten, Oktav-Geisternoten |
| `tests/test_midi_export.py` | Noten + CC64 in Ausgabe |
| `tests/test_basic_pitch_backend.py` | Hinweis bei fehlendem Extra; Mapping der Events |
| `tests/test_bytedance_backend.py` | Mapping der Events (gemockt), Checkpoint-Auflösung |
| `tests/test_cli.py` | End-to-End über `CliRunner` mit Fake-Backend |
| `tests/integration/test_real_backends.py` | `@pytest.mark.slow`: echte Modelle auf kurzem Clip |
| `tests/integration/test_accuracy.py` | `@pytest.mark.slow`: Note-F1 ≥ 0,90 auf MAESTRO-Paar aus `data/testset/maestro/` (Skip, falls nicht vorhanden) |

## Files to Modify
| File | Change Description |
|------|--------------------|
| `README.md` | Installationsanleitung (venv 3.12, Basic-Pitch-Zweischritt), Nutzung von `transcribe`, Lizenzhinweise (ByteDance-Code MIT, Checkpoint-Lizenz laut Zenodo-Seite, Basic Pitch Apache-2.0) |
| `docs/roadmap.md` | Status M0+M1 nach Abschluss auf „implemented“ |
| `docs/features/transcribe-audio-to-midi.md` | `status: implemented` nach Abschluss |

## Data Model Changes
`src/audio2score/model.py` (frozen dataclasses):

```python
@dataclass(frozen=True)
class Note:
    pitch: int        # MIDI 21–108
    onset: float      # Sekunden
    offset: float     # Sekunden, Tasten-Offset (> onset)
    velocity: int     # 1–127

@dataclass(frozen=True)
class PedalEvent:     # Sustain-Pedal
    onset: float
    offset: float

@dataclass
class NoteList:
    notes: list[Note]               # sortiert nach (onset, pitch)
    pedals: list[PedalEvent]
    duration: float                 # Audiolänge in s
    backend: str                    # z. B. "bytedance"
    backend_version: str            # z. B. "0.0.6+note_F1=0.9677"
    def to_dict() / from_dict() / to_json(path) / from_json(path)
```

Cache-JSON: `{"schema": 1, "notelist": {...}}`. Ein anderer `schema`-Wert wird als ungültig behandelt und neu berechnet.

## API / Interface Changes

**Transcriber-Protokoll** (`transcribe/base.py`):
```python
class Transcriber(Protocol):
    name: str
    version: str                    # fließt in den Cache-Schlüssel ein
    def transcribe(self, audio: np.ndarray, sample_rate: int) -> NoteList: ...

class BackendUnavailableError(Exception): ...   # Extra fehlt, mit Installationshinweis
class ModelDownloadError(Exception): ...
```
Registry: `get_transcriber(name: str, **options) -> Transcriber` mit `"bytedance"` (Standard) und `"basic-pitch"`; Backends werden lazy importiert.

**Audio** (`audio/load.py`):
```python
SAMPLE_RATE = 16_000
def load_audio(path: Path, sr: int = SAMPLE_RATE) -> np.ndarray  # float32, mono, Peak auf -1 dBFS
def find_ffmpeg() -> str | None      # PATH, sonst imageio_ffmpeg.get_ffmpeg_exe()
class AudioLoadError(Exception): ...
```
Decodierung: wav/flac/ogg/mp3 über `soundfile`. Bei anderen Formaten oder wenn soundfile scheitert: ffmpeg-Subprozess (`-f f32le -ac 1 -ar 16000 pipe:1`). Resampling bei soundfile-Pfad über `librosa.resample`. Stille (Peak ≈ 0) wird nicht normalisiert.

**ByteDance-Checkpoint**: Auflösung in dieser Reihenfolge: `--checkpoint` → `AUDIO2SCORE_CHECKPOINT` → `~/piano_transcription_inference_data/note_F1=0.9677_pedal_F1=0.9186.pth` (Standardort des Pakets, damit vorhandene Downloads wiederverwendet werden). Fehlt die Datei oder ist sie < 1,6e8 Bytes, wird von der Zenodo-URL nach `*.part` geladen und erst nach vollständigem Download umbenannt. Offline gibt es eine `ModelDownloadError` mit URL und Hinweis auf manuelle Ablage.

**Basic Pitch**: Das vorverarbeitete Audio wird als temporäre WAV (22 050 Hz) geschrieben und an `basic_pitch.inference.predict(path, model_or_model_path=build_icassp_2022_model_path(FilenameSuffix.onnx))` übergeben. Mapping `(start, end, pitch, amplitude, _)` → `Note(velocity=clip(round(amplitude*127), 1, 127))`, keine Pedale. Ein `ImportError` führt zu `BackendUnavailableError` mit Text: `pip install -e .[basic-pitch]` und `pip install --no-deps basic-pitch==0.4.0`.

**Cache** (`cache.py`):
```python
def resolve_cache_dir(option: Path | None) -> Path   # Option > AUDIO2SCORE_CACHE > ./cache
def cache_key(audio_path: Path, transcriber: Transcriber) -> str  # sha256(Dateiinhalt) + name + version
def load(cache_dir, key) -> NoteList | None            # None bei fehlend/beschädigt/altem Schema (mit Warnung)
def save(cache_dir, key, notelist) -> None             # atomar über temp-Datei + replace
```

**Cleanup** (`cleanup/notes.py`):
```python
@dataclass(frozen=True)
class CleanupConfig:
    min_duration: float = 0.03        # s
    min_velocity: int = 8
    relative_velocity: float = 0.2    # Anteil am Median der Velocity im ±1-s-Fenster
    ghost_onset_tolerance: float = 0.03
    ghost_velocity_ratio: float = 0.5
def cleanup(nl: NoteList, cfg: CleanupConfig = CleanupConfig()) -> NoteList
```
Geisternote: Pitch = p+12 zu einer gleichzeitigen (±30 ms) Note p mit höherer Velocity und Velocity < 0,5 × deren Velocity. Startwerte; Feintuning am Testset (M2).

**MIDI** (`export/midi.py`): `write_midi(nl, path)` erzeugt eine Spur mit Program 0 (Acoustic Grand), Noten mit Performance-Timing, pro Pedal-Event CC64=127 bei onset und 0 bei offset. Ausgabeordner wird angelegt.

**Pipeline** (`pipeline.py`):
```python
@dataclass
class TranscriptionResult:
    notelist: NoteList     # nach Cleanup (falls aktiv)
    raw_count: int
    cache_hit: bool
    elapsed: float
def transcribe_file(audio_path, backend="bytedance", cache_dir=None, use_cache=True,
                    do_cleanup=True, checkpoint=None) -> TranscriptionResult
```
Bei einem Cache-Treffer wird das Audio **nicht** geladen (der Schlüssel basiert auf dem Datei-Hash). So bleiben Cache-Treffer < 2 s.

**CLI** (`cli.py`):
```
audio2score transcribe AUDIO -o OUT.mid [--backend bytedance|basic-pitch] [--cache-dir DIR]
                       [--no-cache] [--no-cleanup] [--checkpoint PTH]
audio2score --version
```
Ausgabe: Dauer, Backend, Fortschritt (Download: Bytes; Transkription: Statuszeile), danach Zusammenfassung (Notenanzahl roh/bereinigt, Tonumfang als Notennamen, Pedal-Events, Laufzeit, „aus Cache“). Bekannte Fehler (`AudioLoadError`, `BackendUnavailableError`, `ModelDownloadError`, fehlende Datei) → Meldung auf stderr, Exit-Code 1, kein Traceback. Leeres Ergebnis → leere MIDI-Datei + Warnung, Exit-Code 0.

## Implementation Sequence
1. **Umgebung verifizieren (Spike)**: `py -3.12 -m venv .venv`, `torch`, `piano_transcription_inference`, `librosa`, `onnxruntime`, `basic-pitch --no-deps` installieren. Prüfen: ByteDance-Import und Inferenz auf 10 s Testaudio mit CPU, Laufzeit messen; Kompatibilität `torchlibrosa`/`librosa`/`numpy`; Basic Pitch mit ONNX. Ergebnis: funktionierende Versionsgrenzen für `pyproject.toml` (z. B. falls `numpy<2` oder eine `librosa`-Obergrenze nötig ist).
   - Files: keine (Erkenntnisse fließen in Schritt 2)
   - Depends on: nothing
   - **Status: erledigt (2026-10-11).** Ergebnisse (venv mit torch 2.14.1, numpy 2.5.4, librosa 1.0.0, torchlibrosa 0.1.0, onnxruntime 1.31.0, basic-pitch 0.4.0):
     - Alle Pakete importieren unter Python 3.12 und numpy 2.x; keine Obergrenze für `numpy`, `librosa` oder `torchlibrosa` nötig.
     - `piano_transcription_inference` importiert `audioread` auf Modulebene, deklariert es aber nicht (librosa ≥ 1.0 bringt es nicht mehr mit) → `audioread` als eigene Abhängigkeit aufnehmen. Der Paket-eigene `load_audio` wird nicht benutzt (kein Konflikt mit librosa 1.0).
     - `resampy` (Abhängigkeit von Basic Pitch) braucht `pkg_resources`, das in `setuptools ≥ 81` fehlt → im Extra `basic-pitch` zusätzlich `setuptools<81` (die Meldung „pkg_resources is deprecated“ ist nur eine Warnung).
     - Download des Checkpoints per HTTP funktioniert (171 966 578 Bytes, über der 1,6e8-Schwelle des Pakets); Ablage unter `~/piano_transcription_inference_data/` ist bereits erfolgt.
     - ByteDance auf CPU (`device="cpu"`): Modell laden ≈ 3 s, 10 s Audio ≈ 4 s, 5 min Audio ≈ 320 s (≈ 1× Echtzeit). Spitzen-RAM 5 min: ≈ 1,0 GB → blockweises Transkribieren ist nicht nötig. `est_pedal_events` ist bei synthetischem Audio leer (erwartet).
     - Basic Pitch mit ONNX (kein TensorFlow): 10 s Audio ≈ 0,5 s. `predict()` liefert Tupel `(start, end, pitch, amplitude, pitch_bends)`; das Mapping im Plan passt. Die ONNX-Datei liegt im Paket.
     - `imageio_ffmpeg.get_ffmpeg_exe()` liefert ffmpeg 7.1 ohne Systeminstallation.
2. **Projektgerüst**: `pyproject.toml` (hatchling, src-Layout, `requires-python = ">=3.12,<3.13"`; Abhängigkeiten: `torch`, `piano_transcription_inference==0.0.6`, `audioread`, `librosa`, `soundfile`, `imageio-ffmpeg`, `pretty_midi`, `numpy`, `typer`; Extra `basic-pitch`: `onnxruntime`, `resampy>=0.2.2,<0.4.3`, `setuptools<81`, `scikit-learn`, `scipy`, `mir_eval`; Extra `dev`: `pytest`, `ruff`, `mir_eval`; Entry Point; ruff-Regeln; pytest-Marker `slow` per Default abgewählt mit `-m "not slow"`), `__init__.py`. `pip install -e .[dev]`, `audio2score --version` läuft.
   - Files: `pyproject.toml`, `src/audio2score/__init__.py`, `src/audio2score/cli.py` (nur Gerüst)
   - Depends on: Step 1
3. **Datenmodell** (TDD): `Note`/`PedalEvent`/`NoteList` mit Validierung (offset > onset, Pitch-/Velocity-Bereich) und JSON-Roundtrip.
   - Files: `model.py`, `tests/test_model.py`
   - Depends on: Step 2
4. **Audio laden** (TDD): synthetische Testdateien in `tmp_path` (wav stereo 44,1 kHz, flac; mp3/m4a über ffmpeg erzeugt, falls verfügbar). Tests: Mono, 16 kHz, Peak, Stille, fehlende Datei, unlesbare Datei.
   - Files: `audio/load.py`, `tests/test_audio_load.py`, `tests/conftest.py`
   - Depends on: Step 2
5. **MIDI-Export** (TDD): Rückleseprüfung mit `pretty_midi` (Noten, CC64-Paare, leere Liste ergibt gültige Datei).
   - Files: `export/midi.py`, `tests/test_midi_export.py`
   - Depends on: Step 3
6. **Cache** (TDD): Präzedenz Option > Umgebungsvariable > Default; Schlüssel ändert sich mit Inhalt/Backend/Version; beschädigtes JSON und altes Schema ergeben `None` und werden überschrieben.
   - Files: `cache.py`, `tests/test_cache.py`
   - Depends on: Step 3
7. **Backend-Schnittstelle + ByteDance**: Protokoll, Registry, Checkpoint-Auflösung und -Download, Event-Mapping. Unit-Tests mit gemocktem `PianoTranscription` und gemocktem Download; Slow-Test mit echtem Modell.
   - Files: `transcribe/__init__.py`, `transcribe/base.py`, `transcribe/bytedance.py`, `tests/test_bytedance_backend.py`, `tests/integration/test_real_backends.py`
   - Depends on: Steps 3, 4
8. **Basic-Pitch-Backend**: lazy Import, Hinweis bei fehlendem Extra (Test über `monkeypatch` von `sys.modules`), Mapping-Test mit gemocktem `predict`; Slow-Test, falls installiert.
   - Files: `transcribe/basic_pitch.py`, `tests/test_basic_pitch_backend.py`, `tests/integration/test_real_backends.py`
   - Depends on: Step 7
9. **Aufräumen** (TDD): je eine Regel pro Test; `--no-cleanup`-Pfad unverändert.
   - Files: `cleanup/notes.py`, `tests/test_cleanup.py`
   - Depends on: Step 3
10. **Pipeline + CLI**: `transcribe_file()` und Befehl `transcribe` mit allen Optionen, Fehlerbehandlung, Zusammenfassung. CLI-Tests mit Fake-Backend (registriert per Fixture): erster Lauf vs. Cache-Treffer (Backend nicht aufgerufen), `--no-cache`, `--no-cleanup`, `--cache-dir` vs. Umgebungsvariable, fehlende Datei, nicht installiertes Basic Pitch, leeres Ergebnis.
    - Files: `pipeline.py`, `cli.py`, `tests/test_cli.py`
    - Depends on: Steps 4–9
11. **Genauigkeitstest + Doku**: `test_accuracy.py` (mir_eval `precision_recall_f1_overlap` mit `offset_ratio=None`, Onset ±50 ms) auf MAESTRO-Paar, falls vorhanden. README (Installation, Nutzung, Lizenzen), Status in Spec/Roadmap/Plan aktualisieren. Manuelle Abnahme: eigene Aufnahme transkribieren, MIDI anhören.
    - Files: `tests/integration/test_accuracy.py`, `README.md`, `docs/roadmap.md`, `docs/features/transcribe-audio-to-midi.md`, dieser Plan
    - Depends on: Step 10

## Umsetzungsstand (2026-10-11)
Schritte 1–11 sind umgesetzt (73 schnelle Tests, 3 Slow-Tests grün, `ruff` sauber). Der Status bleibt `approved`, bis offen ist:
- Genauigkeitstest (Note-F1 ≥ 0,90): **erfüllt** auf drei MAESTRO-v3-Stücken aus dem Test-Split (per HTTP-Range aus dem Zip geladen, in `data/testset/maestro/`): Chopin Etüde Op. 10/9 F1 0,982, Scarlatti K. 525 F1 0,967, Schubert Impromptu Op. 90/4 F1 0,988 (mit Aufräumen; roh 0,981 / 0,965 / 0,988). Einschränkung: Studioqualität; Handy-Aufnahmen und Internet-Mitschnitte sind damit nicht abgedeckt.
- Manuelle Abnahme: eigene Aufnahme und Internet-Mitschnitt transkribieren und anhören; Offline-Verhalten (Checkpoint umbenennen, Netz trennen).
- Pedal-Erkennung ist nur mit synthetischem Audio (ohne Pedal) gelaufen, nicht an echtem Klavier.
- `--no-cache` liest und schreibt den Cache nicht (in der Spec nicht festgelegt).

## Test Strategy
- **Unit** (schnell, Standard-`pytest`, keine Modelle, kein Netzwerk): Datenmodell, Audio laden, Cache, Cleanup, MIDI-Export, Backend-Mapping mit Mocks, CLI mit Fake-Backend.
- **Integration** (`pytest -m slow`): echte Backends auf kurzem Clip (prüft: läuft auf der CPU, liefert gültige `NoteList`); Genauigkeit auf MAESTRO-Paar (Akzeptanzkriterium F1 ≥ 0,90, Skip ohne Daten); Cache-Treffer < 2 s mit echtem Backend.
- **Manuell**: eigene Aufnahme (Handy) und ein Internet-Mitschnitt transkribieren, MIDI in einem Player/MuseScore prüfen; Offline-Verhalten durch Umbenennen des Checkpoints und Trennen des Netzes prüfen.
- Zuordnung der Akzeptanzkriterien: hörbar korrekt → manuell; F1 → `test_accuracy`; Cache < 2 s → `test_cli` + slow; Basic Pitch / fehlendes Extra → `test_basic_pitch_backend` + `test_cli`; CC64 → `test_midi_export`; `--no-cleanup` → `test_cli`; Cache-Ort → `test_cache` + `test_cli`; JSON-Roundtrip → `test_model`.

## Risks & Open Questions
- **Abhängigkeitskonflikte unter Python 3.12** (`torchlibrosa` mit neuem `librosa`, `numpy` 2.x): Schritt 1 klärt das vor jeder Implementierung. Notfalls die Versionen pinnen.
- **Basic Pitch nur per `--no-deps`**: fragil bei künftigen Versionen → auf `==0.4.0` pinnen und im README dokumentieren. Bleibt das Extra unter 3.12 trotzdem defekt, wird das dokumentiert (Spec-Entscheidung), das ByteDance-Backend ist nicht betroffen.
- **Modellgewichte**: 165 MB Download, Zenodo kann langsam oder nicht erreichbar sein → Fortschritt, `.part`-Datei, manuelle Ablage dokumentiert.
- **CPU-Speicher und Laufzeit bei langen Aufnahmen**: Im Spike gemessen: 5 min Audio ≈ 320 s und ≈ 1,0 GB Spitzen-RAM → RAM unkritisch, Blockverarbeitung entfällt. Laufzeit ≈ 1× Echtzeit; ein 5-Minuten-Stück braucht beim ersten Lauf also ca. 5 Minuten (deshalb der Cache). Die Spec-Annahmen zur Laufzeit gegebenenfalls prüfen.
- **Cleanup-Schwellen** sind geschätzt → am Testset (M2) kalibrieren.
- [ ] MAESTRO wird nur als Gesamtarchiv (~100 GB) angeboten. Für den Genauigkeitstest genügen 1–3 Stücke (wav + midi) in `data/testset/maestro/`. Woher nehmen: Archiv einmal laden und Teile extrahieren, oder vorerst eigene Einspielung eines Stücks mit vorhandener MIDI-Referenz?
