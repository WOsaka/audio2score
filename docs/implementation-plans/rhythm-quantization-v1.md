---
title: "Implementation Plan: Rhythmus-Quantisierung v1"
feature_spec: docs/features/rhythm-quantization-v1.md
status: approved   # pending-approval | approved | implemented
created: 2026-10-12
updated: 2026-10-12
---

# Implementation Plan: Rhythmus-Quantisierung v1 (M3)

## Summary
Teil B entsteht als Kette reiner Funktionen auf kleinen Datenklassen: `Beats` (Zeiten aus `beat_this`) → `Grid` (Taktart, Phase, fortgesetztes Beat-Raster) → `QNote` (Position und Dauer in ganzen Sechzehnteln) → zwei Hände → music21-Score → drei Exporter. Nur der erste Schritt braucht ein Modell; sein Ergebnis wird wie die Noten im Cache abgelegt (Schlüssel: Audio-Hash + Tracker + Version). Alles danach rechnet mit ganzen Zahlen, ist deterministisch und wird mit synthetischen Beats und Noten getestet.

Die Beat-Erkennung liegt hinter einem Protokoll `BeatTracker` (analog zu `Transcriber`), damit später eine Schätzung aus Onsets für reinen MIDI-Eingang dazukommen kann. `pipeline.score_file()` verbindet Teil A (Cache oder Transkription) mit Teil B; die CLI bekommt `score` und `testset score`.

Geprüft am 2026-10-12: `beat_this` 1.1.0 liegt auf PyPI (Abhängigkeiten `torch>=2`, `torchaudio`, `einops`, `rotary-embedding-torch`, `soxr`, `numpy`). In der venv sind `torch` 2.14.1 und `soxr` vorhanden, `torchaudio` und `music21` fehlen. `mido` ist da (über `pretty_midi`) und schreibt das quantisierte MIDI mit Tempo-Map.

## Files to Create
| File | Purpose |
|------|---------|
| `src/audio2score/rhythm/__init__.py` | Paket; `get_beat_tracker(name)` (Registry wie bei `transcribe`) |
| `src/audio2score/rhythm/base.py` | `Beats`, Protokoll `BeatTracker`, `RhythmError` |
| `src/audio2score/rhythm/beat_this.py` | `BeatThisTracker`: lazy Import, Checkpoint `final0`, CPU, ohne DBN |
| `src/audio2score/rhythm/meter.py` | `parse_time_sig()`, `detect_meter()`, `build_grid()` (Phase, Auftakt, Fortsetzung des Rasters) |
| `src/audio2score/rhythm/quantize.py` | `quantize()`: Sekunden → Sechzehntel-Positionen |
| `src/audio2score/score/__init__.py` | Paket |
| `src/audio2score/score/hands.py` | `split_hands()`: Split am mittleren C mit Hysterese und Spannweitenlimit |
| `src/audio2score/score/voices.py` | `single_voice()`: Akkorde bilden, Dauern am nächsten Onset kappen, Dubletten zusammenlegen |
| `src/audio2score/score/build.py` | `build_score()`: music21-Score mit zwei Systemen, Takten, Haltebögen, Pausen |
| `src/audio2score/export/musicxml.py` | `write_musicxml()` |
| `src/audio2score/export/quantized_midi.py` | `write_quantized_midi()` mit Tempo-Map (mido) |
| `src/audio2score/export/beats.py` | `write_beats_json()` |
| `tests/test_meter.py`, `tests/test_quantize.py`, `tests/test_hands.py`, `tests/test_voices.py`, `tests/test_score_build.py` | Unit-Tests Teil B (synthetisch) |
| `tests/test_score_exports.py` | MusicXML wieder einlesbar, MIDI-Tempo-Map, Beat-JSON |
| `tests/test_beat_this_tracker.py` | Tracker mit gefälschtem `beat_this`-Modul (wie die Backend-Tests aus M1) |
| `tests/test_score_pipeline.py` | `score_file` mit Fake-Backend und Fake-Tracker: Cache-Treffer, Fehlerfälle |
| `tests/test_cli_score.py` | CLI `score` und `testset score`: Ausgabe, Exit-Codes |
| `tests/integration/test_score_real.py` | `@pytest.mark.slow`: echtes `beat_this`, Testset → einlesbares MusicXML |

## Files to Modify
| File | Change Description |
|------|--------------------|
| `pyproject.toml` | `beat_this`, `torchaudio`, `music21` in `dependencies` |
| `src/audio2score/cache.py` | Schlüssel-Funktion verallgemeinern (`cache_key(audio, name, version)`-Kern, bestehende Signatur bleibt), dazu `load_beats()` / `save_beats()` mit eigenem Dateinamen-Suffix |
| `src/audio2score/pipeline.py` | `cached_beats()`, `detect_beats()`, `score_file()` → `ScoreResult` |
| `src/audio2score/testset/run.py` | `score_all()` und `ScoreRow` (erkannte und Soll-Werte) |
| `src/audio2score/cli.py` | Befehl `score`, Unterbefehl `testset score` |
| `README.md` | Abschnitt „Partitur erzeugen“, Installationshinweis `torchaudio` |
| `docs/roadmap.md`, `docs/features/rhythm-quantization-v1.md` | Status nach Abschluss |

## Data Model Changes

```python
# rhythm/base.py
@dataclass(frozen=True)
class Beats:
    times: list[float]        # Sekunden, aufsteigend
    downbeats: list[float]    # Teilmenge von times (auf den nächsten Beat eingerastet)
    tracker: str
    tracker_version: str      # Paketversion + Checkpoint, fließt in den Cache-Schlüssel ein

class BeatTracker(Protocol):
    name: str
    version: str
    def track(self, audio: np.ndarray, sample_rate: int) -> Beats: ...

class RhythmError(Exception): ...   # keine Noten, zu wenige Beats

# rhythm/meter.py
@dataclass(frozen=True)
class Meter:
    numerator: int
    denominator: int          # 4 oder 8
    beats_per_bar: int        # 3/4 → 3; 6/8 → 2 (punktierte Viertel) oder 6 (Achtel)
    steps_per_beat: int       # Sechzehntel pro Beat: 4 (Viertel), 6 (punktierte Viertel), 2 (Achtel)
    source: Literal["detected", "given", "default"]

@dataclass(frozen=True)
class Grid:
    meter: Meter
    beat_times: list[float]   # fortgesetzt vor den ersten / nach dem letzten erkannten Beat
    first_bar_beat: int       # Index des ersten Taktanfangs in beat_times
    pickup_steps: int         # Länge des Auftakts in Sechzehnteln (0 = kein Auftakt)
    tempo_bpm: float          # Median der Beat-Abstände, auf Viertel umgerechnet
    irregular_share: float    # Anteil der Takte, deren erkannter Downbeat nicht zur Phase passt
    @property
    def steps_per_bar(self) -> int: ...

# rhythm/quantize.py
@dataclass(frozen=True)
class QNote:
    pitch: int
    start: int                # Sechzehntel ab Partituranfang (Auftakt-Anfang = 0)
    duration: int             # Sechzehntel, >= 1
    velocity: int
```
Positionen sind ganze Zahlen; Brüche und Rundungsfehler gibt es nach der Quantisierung nicht mehr.

**Beat-Cache**: `cache/<sha256>-beats-<tracker>-<version>.json` mit `{"schema": 1, "beats": {"times": [...], "downbeats": [...], ...}}`. Beschädigte oder veraltete Einträge werden wie beim Noten-Cache mit Warnung neu berechnet.

**Beat-Datei** (`<name>.beats.json`):
```json
{"audio": "aufnahme.mp3", "tracker": "beat_this", "tracker_version": "1.1.0-final0",
 "time_sig": "3/4", "time_sig_source": "detected", "tempo_bpm": 92.4,
 "pickup_steps": 4, "bars": 64, "irregular_share": 0.03,
 "beats": [{"time": 0.512, "bar": 0, "beat": 3, "downbeat": false, "detected": true}]}
```
`detected: false` markiert fortgesetzte Beats. Eine zusätzliche Marker-Datei für Audacity gibt es nicht (offene Frage der Spec, bei Bedarf später aus dem JSON ableitbar).

## API / Interface Changes

### CLI
```
audio2score score AUDIO -o ORDNER [--time-sig 3/4] [--backend bytedance] [--cache-dir C] [--no-cache] [--checkpoint P]
audio2score testset score -o ORDNER [--manifest P] [--data-dir D] [--backend bytedance] [--cache-dir C] [--only ID ...]
```
- `--time-sig`: erlaubt `2/4`, `3/4`, `4/4`, `3/8`, `6/8`, `9/8`, `12/8`; sonst `BadParameter` mit dieser Liste.
- `score` gibt aus: Backend, „Transkribiere ...“ / „Erkenne Beats ...“ (nur bei Cache-Fehltreffer), Taktart (erkannt | vorgegeben | Standard), Tempo, Takte, Auftakt, Noten rechte/linke Hand, Warnungen (uneinheitliche Takte, keine Downbeats), Laufzeit, drei Pfade. Ausgabedateien heißen nach dem Audio-Dateistamm.
- `testset score`: Noten **nur aus dem Cache** (sonst „nicht transkribiert“, übersprungen). Beats werden beim ersten Lauf berechnet und gecacht. `time_sig` aus dem Manifest wird nicht als Hinweis benutzt, nur verglichen. Tabelle: `Stück | Taktart (ist/soll) | Takte (ist/soll) | Auftakt | Status`. Soll-Taktart aus `time_sig`, Soll-Taktzahl aus `ref_annotations` (Anzahl `db`-Zeilen; passt zeitlich zum Audio-Ausschnitt, anders als das Referenz-MusicXML). Jedes MusicXML wird mit music21 wieder eingelesen. Exit-Code 1, wenn ein Stück scheitert; die übrigen laufen weiter.

### Bibliothek
```python
rhythm.get_beat_tracker(name="beat_this") -> BeatTracker
meter.parse_time_sig("3/4") -> tuple[int, int]
meter.build_grid(beats: Beats, notes: list[Note], time_sig: tuple[int, int] | None) -> Grid
quantize.quantize(notes: list[Note], grid: Grid) -> list[QNote]
hands.split_hands(notes: list[QNote]) -> tuple[list[QNote], list[QNote]]   # (rechts, links)
voices.single_voice(notes: list[QNote]) -> list[QNote]
build.build_score(right, left, grid, title) -> music21.stream.Score
export.write_musicxml(score, path); write_quantized_midi(right, left, grid, path); write_beats_json(grid, beats, path, audio_name)
pipeline.cached_beats(audio_path, cache_dir) -> Beats | None
pipeline.score_file(audio_path, out_dir, time_sig=None, backend="bytedance", cache_dir=None,
                    use_cache=True, checkpoint=None, on_download=None, on_transcribe=None,
                    on_beats=None, tracker=None) -> ScoreResult
testset.run.score_all(manifest, backend, cache_dir, out_dir, only=None, on_start=None, on_result=None) -> list[ScoreRow]
```
`ScoreResult`: Pfade, `Grid`, Taktzahl, Noten pro Hand, `warnings: list[str]`, Cache-Treffer für Noten und Beats, Laufzeit.

## Algorithmen im Detail

### Beats (`beat_this.py`)
`Audio2Beats(checkpoint_path="final0", device="cpu", dbn=False)`, Aufruf mit Mono-Signal bei 22,05 kHz (`load_audio(path, 22_050)`). Ohne DBN, weil das `madmom` bräuchte. Fehlender Import → `BackendUnavailableError` mit Installationshinweis, Fehler beim Laden der Gewichte → `ModelDownloadError` (beide aus `transcribe/base.py` wiederverwendet). Downbeats werden auf den nächsten Beat eingerastet.

### Taktart und Raster (`meter.py`)
1. Weniger als 4 Beats → `RhythmError` (Hinweis: Stück zu kurz oder frei gespielt).
2. Beats pro Takt = Abstand aufeinanderfolgender Downbeats in Beat-Indizes; Modus.
3. Ohne `--time-sig`: Modus ∈ {2, 3, 4} → n/4; sonst (auch ohne Downbeats) 4/4 mit `source="default"` und Warnung.
4. Mit `--time-sig n/4`: `beats_per_bar = n`, 4 Sechzehntel pro Beat.
   Mit `n/8`: Ist der erkannte Modus `n`, zählen die Beats als Achtel (2 Sechzehntel); ist er `n/3` oder unklar, bei 6/8, 9/8, 12/8 als punktierte Viertel (6 Sechzehntel), bei 3/8 als Achtel.
5. Phase = häufigster Wert von (Downbeat-Index mod `beats_per_bar`); ohne Downbeats Phase des ersten Beats. `irregular_share` = Anteil der Downbeats mit anderer Phase; über 20 % → Warnung.
6. Raster fortsetzen: vor dem ersten und nach dem letzten Beat mit dem Median der vier nächstgelegenen Abstände, bis alle Noten (Onset und Offset) abgedeckt sind und das Ende auf einem Taktstrich liegt.
7. Partituranfang: Takt, in dem die erste Note liegt. Liegt die erste Note in der zweiten Takthälfte, beginnt die Partitur am Beat dieser Note (Auftakt, `pickup_steps` = Rest bis zum Taktstrich); sonst voller Takt mit Pause davor. Leere Takte vor der ersten Note (Beats in der Stille) entfallen.

### Quantisierung (`quantize.py`)
Für jede Zeit `t`: Beat-Intervall `i` per Bisektion, `pos = i·s + round((t − b_i)/(b_{i+1} − b_i)·s)` mit `s = steps_per_beat`, abzüglich Partituranfang. Onset und Offset getrennt; `duration = max(1, off − on)`.

### Handtrennung (`hands.py`)
Noten nach quantisiertem Onset gruppieren. Konstanten `SPLIT = 60`, `HYSTERESIS = 5`, `MAX_SPAN = 14` (None):
- Tonhöhe ≥ `SPLIT + HYSTERESIS` → rechts, ≤ `SPLIT − HYSTERESIS` → links.
- Dazwischen: zur Hand, deren zuletzt gespielte Noten (gleitender Mittelwert) näher liegen; ohne Vorgeschichte entscheidet `SPLIT`.
- Überschreitet eine Hand in einer Gruppe `MAX_SPAN`, wandert ihre äußerste Note zur anderen Hand zur Mitte hin, solange das dort passt.
Die Werte werden in Schritt 9 am Testset geprüft und hier nachgetragen.

### Eine Stimme pro Hand (`voices.py`)
Gleiche Tonhöhe auf derselben Position → eine Note (längste Dauer, lauteste Velocity). Gleicher Onset → Akkord mit der längsten Dauer der Gruppe. Jede Dauer endet spätestens am nächsten Onset derselben Hand.

### Partitur (`build.py`)
Takte werden selbst gebaut, nicht über `makeMeasures`: So sind Auftakt (Takt 0, verkürzt), Taktstrich-Teilung mit Haltebögen und Pausenfüllung unter eigener Kontrolle und exakt testbar. Innerhalb eines Takts zerlegt music21 nicht darstellbare Dauern (z. B. 5 Sechzehntel) in gebundene Noten und setzt Balken (`makeNotation`-Bausteine: `splitAtDurations`, `makeBeams`). Zwei `PartStaff` mit Klammer (`layout.StaffGroup`) ergeben im MusicXML eine Klavierstimme mit zwei Systemen. Erster Takt: Schlüssel, Taktart, `MetronomeMark(round(tempo_bpm))`. Vorzeichen in der music21-Standardschreibweise (C♯, E♭, F♯, G♯, B♭), keine Tonartvorzeichnung.

### Quantisiertes MIDI (`quantized_midi.py`)
mido, 480 Ticks pro Viertel, Typ 1: Tempo-Spur + rechte Hand + linke Hand. Pro Beat ein `set_tempo` aus dem Beat-Abstand (umgerechnet auf Viertel), dazu `time_signature`. Davor ein Vorlauf von genau einem Takt, dessen Tempo so gesetzt ist, dass er bis zum Partituranfang in der Aufnahme dauert: Das MIDI startet bei Audio-Zeit 0 und bleibt synchron, die Taktstriche stimmen. Bei Auftakt wird der Vorlauf um den fehlenden Taktteil ergänzt.

## Implementation Sequence
1. **Installation und Messung (Spike)** — `beat_this`, `torchaudio` (CPU, passend zu torch 2.14.1), `music21` in `pyproject.toml`; installieren; prüfen, dass `torch` nicht durch einen anderen Build ersetzt wird und die M1-Tests weiterlaufen. `beat_this` auf zwei Testset-Stücken ausführen: Laufzeit auf der CPU, Ort und Größe der Gewichte, Format der Rückgabe. Beat-Ebene bei der Fuge BWV 856 (3/8) gegen die ASAP-Annotationen festhalten. Ergebnisse hier im Plan notieren (Abschnitt Umsetzungsstand).
   - Files: `pyproject.toml`
   - Depends on: nothing
2. **Datenklassen, Protokoll, Tracker, Beat-Cache** (TDD) — `Beats`, `BeatTracker`, `BeatThisTracker` gegen ein gefälschtes Modul; `cache.load_beats`/`save_beats`; `pipeline.cached_beats`/`detect_beats` (Tracker wird bei Cache-Treffer nicht aufgerufen).
   - Files: `rhythm/__init__.py`, `rhythm/base.py`, `rhythm/beat_this.py`, `cache.py`, `pipeline.py`, `tests/test_beat_this_tracker.py`, `tests/test_cache.py`
   - Depends on: Step 1
3. **Taktart und Raster** (TDD) — `parse_time_sig`, `detect_meter`, `build_grid`: Modus, Phase mit Ausreißern, keine Downbeats, Vorgabe n/4 und n/8, Fortsetzung, Auftakt-Regel, leere Takte am Anfang, zu wenige Beats.
   - Files: `rhythm/meter.py`, `tests/test_meter.py`
   - Depends on: Step 2 (nur `Beats`)
4. **Quantisierung** (TDD) — exakte Noten bleiben exakt; ±40 ms Abweichung rundet richtig; Tempowechsel zwischen Beats; Mindestdauer; Noten vor dem ersten und nach dem letzten erkannten Beat.
   - Files: `rhythm/quantize.py`, `tests/test_quantize.py`
   - Depends on: Step 3
5. **Handtrennung und Stimmen** (TDD) — klare Lagen, Noten im Hysteresebereich folgen der Hand, Spannweitenlimit, leere Hand; Akkordbildung, Kappen am nächsten Onset, Dubletten.
   - Files: `score/hands.py`, `score/voices.py`, `tests/test_hands.py`, `tests/test_voices.py`
   - Depends on: Step 4 (nur `QNote`)
6. **Partitur** (TDD) — zwei Systeme, Taktart, Metronom; jeder Takt exakt gefüllt (Summe der Dauern = Taktlänge, Auftakt = `pickup_steps`); Note über den Taktstrich wird gebunden; leere Hand ergibt Ganztaktpausen; 3/4 und 6/8.
   - Files: `score/build.py`, `tests/test_score_build.py`
   - Depends on: Step 5
7. **Exporter** (TDD) — MusicXML schreiben und mit music21 wieder einlesen (Taktzahl, Taktart, zwei Systeme, Tonhöhen); MIDI: Notenzeiten nach der Tempo-Map liegen auf den Beat-Zeiten (±5 ms); Beat-JSON vollständig.
   - Files: `export/musicxml.py`, `export/quantized_midi.py`, `export/beats.py`, `tests/test_score_exports.py`
   - Depends on: Step 6
8. **Pipeline und CLI `score`** (TDD) — `score_file` mit Fake-Backend und Fake-Tracker: drei Dateien; zweiter Lauf ohne Backend- und Tracker-Aufruf; `--time-sig`; keine Noten / zu wenige Beats → Fehler ohne Dateien; ungültige Taktart; Zielordner wird angelegt.
   - Files: `pipeline.py`, `cli.py`, `tests/test_score_pipeline.py`, `tests/test_cli_score.py`
   - Depends on: Steps 2–7
9. **`testset score` und Echtlauf** — `score_all` (TDD mit Fakes: übersprungen, gescheitert, Soll-Werte aus Manifest und Annotationen), dann real auf allen 12 Stücken. Tabelle (Taktart und Takte ist/soll) in den Umsetzungsstand; Parameter der Handtrennung prüfen und ggf. anpassen. Slow-Test: alle transkribierten Stücke ergeben ein einlesbares MusicXML.
   - Files: `testset/run.py`, `cli.py`, `tests/test_testset_run.py`, `tests/test_cli_score.py`, `tests/integration/test_score_real.py`
   - Depends on: Step 8
10. **Manuelle Abnahme** (User) — 2–3 Stücke in MuseScore 4 öffnen (keine Fehlermeldung, erkennbar, nachspielbar), quantisiertes MIDI gegen die Aufnahme hören. Vorschlag: Bach-Präludium BWV 846, Anthem of Rain (Pop), Mozart KV 332 (3/4).
    - Depends on: Step 9
11. **Doku und Abschluss** — README, Status in Spec, Plan, Roadmap; `ruff check . && ruff format .`, `pytest`, `pytest -m slow`; Skill `verification-before-completion`.
    - Files: `README.md`, `docs/roadmap.md`, `docs/features/rhythm-quantization-v1.md`, dieser Plan
    - Depends on: Step 10

## Test Strategy
- **Unit** (schnell, ohne Netz, ohne Modelle): Schritte 2–8 mit synthetischen Beats (konstantes Tempo, Accelerando, fehlende Downbeats, Ausreißer) und synthetischen Noten. Fake-Tracker und Fake-Backend zählen ihre Aufrufe, damit „ohne Modelllauf“ prüfbar ist.
- **Integration** (`pytest -m slow`, Skip ohne Daten bzw. Cache): echtes `beat_this` auf einem kurzen Stück (Beats plausibel, Tempo im erwarteten Bereich); `testset score` auf dem echten Testset → jedes MusicXML einlesbar.
- **Manuell**: Schritt 10; dazu `--time-sig` auf einem Stück mit falsch erkannter Taktart.
- **Zuordnung der Akzeptanzkriterien**:
  - drei Dateien ohne Modelllauf / mit Berechnung → `test_score_pipeline`
  - zwei Systeme, Taktart, Metronom, volle Takte → `test_score_build`
  - wieder einlesbar → `test_score_exports`, slow; MuseScore → manuell
  - `--time-sig` → `test_meter`, `test_cli_score`
  - synthetisches Stück exakt → `test_quantize`, `test_score_build`
  - Auftakt → `test_meter`, `test_score_build`
  - alle 12 Stücke → `test_score_real` (slow) und Echtlauf in Schritt 9
  - Taktart/Taktzahl plausibel → Tabelle aus Schritt 9 (Richtwert)
  - MIDI synchron → `test_score_exports` (Zeiten) und manuell
  - Tests ohne Modell und Netz → gesamte Unit-Suite

## Risks & Open Questions
- **`torchaudio` unter Windows/CPU**: muss exakt zur torch-Version passen; ein falscher Index kann torch ersetzen. Gegenmittel: Schritt 1 zuerst, Version festhalten, M1-Tests danach laufen lassen. Notlösung: Mel-Spektrogramm-Pfad von `beat_this` prüfen bzw. `madmom`-freien Ersatztracker (librosa) hinter demselben Protokoll.
- **Laufzeit und Gewichte von `beat_this`**: unbekannt bis Schritt 1; durch den Cache nur einmal pro Datei relevant.
- **Beat-Ebene bei n/8**: Die Regel in „Taktart und Raster“ ist eine Annahme; Schritt 1 prüft sie an BWV 856 (3/8). Im Testset gibt es kein 6/8-Stück, `--time-sig 6/8` ist daher nur synthetisch getestet.
- **Falsche Taktart bei Klassik mit Rubato**: erwartbar (Debussy, Chopin). Kein Abbruch; `--time-sig` und die Soll/Ist-Tabelle machen es sichtbar.
- **Halbes/doppeltes Tempo** der Beat-Erkennung: führt zu lesbaren, aber doppelt/halb so langen Notenwerten. In M3 nur dokumentiert; `--tempo-hint` ist nicht Teil des Features.
- **music21 und selbst gebaute Takte**: `splitAtDurations`/`makeBeams` können bei ungewöhnlichen Dauern unschöne, aber gültige Ergebnisse liefern. Gegenmittel: Wiedereinlese-Test über alle Testset-Stücke.
- **Lizenz**: Code von `beat_this` MIT; Lizenz der Gewichte in Schritt 1 nachsehen und im README vermerken (Hobbyprojekt, nicht kommerziell).
- **Abweichung von der Spec**: Vorzeichen in music21-Standardschreibweise (gemischt ♯/♭) statt „nur Kreuze“; Marker-Datei für Audacity entfällt.
- [ ] Reicht für `testset score` die Soll-Taktzahl aus den ASAP-Annotationen, oder soll zusätzlich das Referenz-MusicXML gezählt werden?

## Umsetzungsstand

### Schritt 1 — Spike (2026-10-12)
- **Installation**: `uv pip install music21 beat_this` zog `torchaudio 2.11.0` nach; `torch` blieb bei 2.14.1. Auf dem CPU-Index gibt es `torchaudio` nur bis 2.11, eine exakt passende Version existiert nicht. Import von `torchaudio` und `beat_this.inference` und die Inferenz laufen trotzdem. M1-Tests: 177 grün.
- **Gewichte**: `final0.ckpt`, 81 MB, Download beim ersten Lauf nach `~/.cache/torch/hub/checkpoints/` (von `cloud.cp.jku.at`, Fortschritt auf stdout). Paketcode MIT; die Lizenz der Gewichte steht nicht in den Paket-Metadaten (noch nachsehen, vor README-Vermerk).
- **Rückgabe**: `Audio2Beats(...)(signal, sr)` → `(beats, downbeats)`, zwei `float64`-Arrays in Sekunden. Downbeats werden hier noch nicht auf Beats eingerastet (der Tracker rastet selbst ein).
- **Laufzeit (CPU)**: Modell laden 7,4 s; BWV 856 (69 s Audio) 3,3 s; Mozart K332 (273 s) 10,3 s, also etwa 0,04 × Echtzeit.
- **Beat-Ebene bei 3/8 (BWV 856)**: 215 Beats, genau so viele wie in der ASAP-Annotation (Achtel-Beats); 62 von 71 Downbeat-Abständen sind 3 Beats. Die Annahme „Modus n bei n/8 → Beats sind Achtel“ stimmt hier. Mozart K332 (3/4): 223 von 230 Abständen sind 3; 688 Beats gegen 686 in der Referenz.
