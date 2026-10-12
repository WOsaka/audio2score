---
title: "Implementation Plan: Testset"
feature_spec: docs/features/testset.md
status: approved   # pending-approval | approved | implemented
created: 2026-10-12
updated: 2026-10-12
---

# Implementation Plan: Testset (M2)

## Summary
Ein eingechecktes YAML-Manifest (`testset/manifest.yaml`) beschreibt alle Stücke: Metadaten, lokale Pfade unter `data/testset/` und, für automatisch ladbare Stücke, einen `fetch`-Block mit der Quelle. Ein neues Paket `audio2score.testset` liest und validiert das Manifest, lädt ASAP- und MAESTRO-Stücke (`fetch`), prüft die Dateien (`check`), füllt den Teil-A-Cache (`transcribe`) und berechnet die Note-F1 nur aus dem Cache (`baseline`). Die Hilfsfunktionen für die F1 wandern aus `tests/integration/test_accuracy.py` nach `audio2score/eval/notes.py`, damit CLI und Test denselben Code nutzen. Die CLI bekommt eine Unter-App `audio2score testset {fetch,check,transcribe,baseline}`.

MAESTRO-Audio wird wie in M1 per HTTP-Range direkt aus dem Zip (108 GB) gelesen: Ein seekbares Datei-Objekt über `Range`-Requests (nur Standardbibliothek: `urllib`, `zipfile`, `io`). Der Server unterstützt `Accept-Ranges: bytes` (geprüft 2026-10-12). ASAP-Dateien kommen einzeln über `raw.githubusercontent.com`, gepinnt auf Commit `afc815c75c42e83a79c03feb6da8a35e77d4c6b8`.

## Files to Create
| File | Purpose |
|------|---------|
| `testset/manifest.yaml` | Das Manifest (eingecheckt), 12–15 Einträge |
| `testset/README.md` | Kurzanleitung: Ablage eigener Aufnahmen, Felder, Befehle |
| `src/audio2score/testset/__init__.py` | Paket |
| `src/audio2score/testset/manifest.py` | Datenmodell `Entry`/`FetchSpec`, `load_manifest()`, Schema-Validierung |
| `src/audio2score/testset/check.py` | Dateiprüfung pro Eintrag: vorhanden, lesbar |
| `src/audio2score/testset/fetch.py` | `RangeFile` (HTTP-Range → seekbar), `fetch_maestro()`, `fetch_asap()`, `fetch_all()` |
| `src/audio2score/testset/run.py` | `transcribe_all()` und `baseline()` (Tabelle + Mittelwerte) |
| `src/audio2score/eval/__init__.py` | Paket |
| `src/audio2score/eval/notes.py` | `note_prf()` / `note_f1()` (mir_eval, Onset ±50 ms, ohne Offsets), `read_midi_notes()` |
| `tests/test_testset_manifest.py` | Validierung: Pflichtfelder, Enums, doppelte IDs, Pfade, `fetch`-Block |
| `tests/test_testset_check.py` | `check` mit synthetischen Dateien (WAV, MIDI, MusicXML, defekte Dateien) |
| `tests/test_testset_fetch.py` | `RangeFile` + Zip-Extraktion gegen lokalen HTTP-Server (`http.server` im Thread); Zuschnitt; Fortsetzen; Fehler |
| `tests/test_testset_run.py` | `transcribe_all`/`baseline` mit Fake-Backend aus dem CLI-Test |
| `tests/test_eval_notes.py` | F1-Hilfsfunktionen (aus `test_accuracy.py` verschoben) |
| `tests/test_cli_testset.py` | CLI-Unterbefehle: Exit-Codes, Ausgabe |
| `tests/integration/test_testset_real.py` | `@pytest.mark.slow`: `check` auf echtem Testset, Plausibilität der F1 (Skip ohne Daten) |

## Files to Modify
| File | Change Description |
|------|--------------------|
| `pyproject.toml` | `pyyaml` und `mir_eval` in `dependencies` (mir_eval bleibt in `dev` überflüssig → entfernen) |
| `src/audio2score/cli.py` | `testset_app = typer.Typer()`, per `app.add_typer(testset_app, name="testset")` |
| `src/audio2score/pipeline.py` | `cached_transcription(audio_path, backend, cache_dir, do_cleanup) -> TranscriptionResult \| None`: nur Cache lesen, kein Modell laden. Gemeinsame Logik mit `transcribe_file` herausziehen |
| `tests/integration/test_accuracy.py` | Importiert `note_f1`/`read_midi_notes` aus `audio2score.eval.notes`; liest MAESTRO-Paare weiterhin aus `data/testset/maestro/` |
| `README.md` | Abschnitt „Testset“ |
| `docs/roadmap.md`, `docs/features/testset.md` | Status nach Abschluss |

## Data Model Changes

### Manifest (`testset/manifest.yaml`)
```yaml
version: 1
data_dir: ../data/testset      # relativ zur Manifest-Datei; per --data-dir überschreibbar
entries:
  - id: asap-bach-prelude-bwv846
    style: classical            # classical | pop | jazz | free
    source: asap                # asap | maestro | own | internet
    quality: studio             # studio | phone | internet
    audio: asap/bach-prelude-bwv846.flac
    ref_midi: asap/bach-prelude-bwv846.mid           # Performance-MIDI, zeitlich passend zum Audio
    ref_musicxml: asap/bach-prelude-bwv846.musicxml
    ref_annotations: asap/bach-prelude-bwv846.txt    # ASAP: Beats/Downbeats/Taktart/Tonart (für M3)
    time_sig: 4/4               # optional
    tempo_hint: 66              # optional
    license: CC BY-NC-SA 4.0
    origin: "ASAP (Shi05M) / MAESTRO v3, 2006"
    fetch:                      # optional; nur für automatisch ladbare Stücke
      asap_folder: Bach/Prelude/bwv_846
      asap_performance: Shi05M
      maestro_audio: 2006/MIDI-Unprocessed_19_R1_2006_01-07_ORIG_MID--AUDIO_19_R1_2006_01_Track01_wav.wav
      start: 0.0                # Ausschnitt im MAESTRO-Audio (s); aus ASAP metadata.csv
      end: 139.12
  - id: maestro-scarlatti-k525
    source: maestro
    audio: maestro/scarlatti-k525.wav
    ref_midi: maestro/scarlatti-k525.midi
    fetch:
      maestro_audio: 2008/MIDI-Unprocessed_09_R3_2008_01-07_ORIG_MID--AUDIO_09_R3_2008_wav--2.wav
    # ...
```
`ref_annotations` und `fetch` ergänzen die Spec: Die Annotationen kosten nichts und liefern die Beat-Referenz für M3. Mit `fetch` bleibt das Manifest die einzige Quelle für den Download.

### Python
```python
Style = Literal["classical", "pop", "jazz", "free"]; Source = ...; Quality = ...

@dataclass(frozen=True)
class FetchSpec:
    maestro_audio: str | None = None   # Pfad im MAESTRO-Zip (ohne Präfix maestro-v3.0.0/)
    asap_folder: str | None = None
    asap_performance: str | None = None
    start: float | None = None
    end: float | None = None

@dataclass(frozen=True)
class Entry:
    id: str; style: Style; source: Source; quality: Quality
    license: str; origin: str
    audio: Path | None; ref_midi: Path | None; ref_musicxml: Path | None; ref_annotations: Path | None
    time_sig: str | None; tempo_hint: float | None; notes: str
    fetch: FetchSpec | None

@dataclass
class Manifest:
    path: Path; data_dir: Path; entries: list[Entry]

class ManifestError(Exception): ...          # mit Liste aller Fehler (Eintrag-ID + Grund)
```
Pfade in `Entry` sind bereits gegen `data_dir` aufgelöst. Die Validierung sammelt alle Fehler, statt beim ersten abzubrechen.

## API / Interface Changes

### CLI
```
audio2score testset fetch     [--manifest P] [--data-dir D] [--only ID ...] [--force]
audio2score testset check     [--manifest P] [--data-dir D]
audio2score testset transcribe [--manifest P] [--data-dir D] [--backend bytedance] [--cache-dir C] [--only ID ...]
audio2score testset baseline  [--manifest P] [--data-dir D] [--backend bytedance] [--cache-dir C] [--no-cleanup]
```
- Standard `--manifest`: `testset/manifest.yaml`, sonst Umgebungsvariable `AUDIO2SCORE_TESTSET`.
- `fetch`: überspringt vorhandene Dateien (fortsetzbar, `--force` lädt neu). Pro Stück eine Zeile mit Fortschritt (MB). Exit-Code 1, wenn mindestens ein Stück scheitert; die übrigen werden trotzdem geladen.
- `check`: pro Eintrag `OK` / `WARN` / `FEHLER` mit Grund, danach eine Zusammenfassung. Exit-Code 1 bei Fehlern im Manifest oder bei Dateien. Fehlende optionale Referenzen sind kein Fehler. Prüfungen: Existenz; Audio per `soundfile.info`, sonst `ffprobe`-artig über `find_ffmpeg()` (`-i` ohne Ausgabe); MIDI per `pretty_midi`; MusicXML per `xml.etree` (wohlgeformt, Wurzel `score-partwise`/`score-timewise`, auch `.mxl` als Zip); Annotationen: Zeilen `float\tfloat\tlabel`.
- `transcribe`: `[3/12] id … aus Cache | transkribiert in 95 s`. Einträge ohne Audio werden mit Hinweis übersprungen, fehlende Dateien mit Warnung. Weitere Fehler pro Stück (z. B. Decodierung) werden gemeldet, danach geht es weiter. Exit-Code 1, wenn ein Stück gescheitert ist.
- `baseline`: Tabelle `id | Stil | Qualität | P | R | F1 | Noten (ref/est)`, danach Mittelwerte pro Stil und pro Qualität (Makro-Mittel über Stücke). Stücke ohne Referenz: „keine Referenz“. Stücke ohne Cache-Eintrag: „nicht transkribiert“ mit Hinweis auf `testset transcribe`. Lädt nie ein Modell.

### Bibliothek
```python
load_manifest(path: Path, data_dir: Path | None = None) -> Manifest
check_entry(entry: Entry) -> list[Issue]           # Issue(level: "warn"|"error", message)
fetch_entry(entry: Entry, force=False, on_progress=None) -> None
transcribe_all(manifest, backend, cache_dir, only=None, on_event=None) -> list[RunResult]
baseline(manifest, backend, cache_dir, do_cleanup=True) -> list[BaselineRow]
pipeline.cached_transcription(...) -> TranscriptionResult | None
eval.notes.note_prf(ref: list[Note], est: list[Note]) -> tuple[float, float, float]
eval.notes.read_midi_notes(path: Path) -> list[Note]
```

### Download-Details
- **MAESTRO:** `https://storage.googleapis.com/magentadata/datasets/maestro/v3.0.0/maestro-v3.0.0.zip`. `RangeFile(io.RawIOBase)` mit `seek`/`readinto` über `Range: bytes=a-b`, Größe per `HEAD`, in `io.BufferedReader` (Puffer 1 MB) gekapselt, damit `zipfile` nicht Byte für Byte anfragt. Das Zip-Zentralverzeichnis (Zip64, ~1 MB) wird einmal pro Lauf gelesen. Eintrag `maestro-v3.0.0/<maestro_audio>` als Stream nach `<ziel>.part`, dann `os.replace`. Mit `start`/`end` wird nach dem Download per `soundfile` zugeschnitten und als FLAC gespeichert (spart ~50 % Platz). Die passende MAESTRO-MIDI (`.midi` gleichen Namens) wird mitgeladen. Bei ASAP-Stücken dient sie nur zur Kontrolle des Versatzes und wird nicht gespeichert.
- **ASAP:** `https://raw.githubusercontent.com/fosfrancesco/asap-dataset/<commit>/<folder>/{xml_score.musicxml, <perf>.mid, <perf>_annotations.txt}`.
- Netzwerkfehler → `FetchError` mit Stück-ID und URL. Teilfertige `.part`-Dateien werden gelöscht. Timeouts 30 s, 3 Wiederholungen pro Range-Request.

## Auswahl der Stücke (Kandidaten)
Wird in Schritt 7 festgelegt und gemessen; Ziel ≤ 60 min Audio gesamt.

| Gruppe | Kandidaten | ca. Dauer |
|---|---|---|
| ASAP (6) | Bach Präludium BWV 846; Bach Fuge BWV 856; Mozart Sonate KV 332, 1. Satz (ASAP `Piano_Sonatas/12-1`); Beethoven op. 81a, 2. Satz (`26-2`); Chopin Etüde op. 10/5; Debussy *Pour le piano*, Prélude. Ersatz: Schumann Kreisleriana 1, Haydn Hob. XVI:39/1 | ~17 min |
| MAESTRO (3) | M1-Stücke, Test-Split: Chopin op. 10/9 (`2011/MIDI-Unprocessed_24_R1_2011_MID--AUDIO_R1-D9_11_Track11_wav.wav`, 125 s, einziger Treffer); Scarlatti K. 525 (`2008/MIDI-Unprocessed_09_R3_2008_01-07_ORIG_MID--AUDIO_09_R3_2008_wav--2.wav`, 66 s, einziger Treffer); Schubert op. 90/4: fünf Fassungen im Test-Split, die M1-Fassung ist nicht festgehalten (siehe Schritt 7) | ~6–9 min |
| Internet (1) | Ivanov, Nocturne op. 9/3 (vorhanden) | ~3 min |
| Eigene / Internet (≥ 3) | Pop, Jazz, Improvisation (liefert der User) | ~10 min |

Taktarten laut ASAP-Annotationen beim Festlegen prüfen. Ziel: neben 4/4 auch 3/4, 2/4 und ein zusammengesetzter Takt (3/8 oder 6/8). Hinweis: Die M1-Dateien in `data/testset/maestro/` sind lokal nicht mehr vorhanden, und ihre MAESTRO-Pfade waren nirgends festgehalten. Ab jetzt hält das Manifest den genauen Pfad im Zip fest (`fetch.maestro_audio`). Die MAESTRO-Einträge legen `fetch` wieder in `maestro/` ab (`<id>.wav` + `.midi`), damit `test_accuracy.py` weiterläuft.

## Implementation Sequence
1. **Abhängigkeiten + Eval-Modul**: `pyyaml`, `mir_eval` nach `dependencies`. `eval/notes.py` mit `note_prf`, `note_f1`, `read_midi_notes` (aus `test_accuracy.py`, TDD: Tests zuerst verschieben). `test_accuracy.py` importiert von dort. Fehlen die Daten, nennt der Skip-Grund die fehlenden Dateien und den Befehl `audio2score testset fetch --only maestro-…`, damit das Überspringen nicht untergeht. Fehlende Dateien meldet zusätzlich `testset check`.
   - Files: `pyproject.toml`, `src/audio2score/eval/*`, `tests/test_eval_notes.py`, `tests/integration/test_accuracy.py`
   - Depends on: nothing
2. **Manifest-Modell + Validierung** (TDD): Laden, Pfade auflösen, alle Fehler sammeln (Pflichtfelder, Enums, doppelte IDs, weder `audio` noch `ref_midi`, `fetch` unvollständig, `start ≥ end`, absolute oder aus `data_dir` herausführende Pfade).
   - Files: `testset/manifest.py`, `tests/test_testset_manifest.py`
   - Depends on: nothing
3. **Dateiprüfung** (TDD): `check_entry` für Audio, MIDI, MusicXML/MXL, Annotationen; synthetische Dateien in `tmp_path`, darunter defekte (abgeschnittenes WAV, Text als `.mid`, kaputtes XML).
   - Files: `testset/check.py`, `tests/test_testset_check.py`
   - Depends on: Step 2
4. **`cached_transcription` in der Pipeline** (TDD): Treffer liefert das Ergebnis mit bzw. ohne Cleanup, ein Fehltreffer `None`. Das Backend wird dabei nicht aufgerufen (Fake-Backend zählt die Aufrufe).
   - Files: `pipeline.py`, `tests/test_pipeline.py` (neu) bzw. vorhandene CLI-Tests
   - Depends on: nothing
5. **Download** (TDD gegen lokalen HTTP-Server mit Range-Unterstützung): `RangeFile` liest beliebige Bereiche korrekt; Zip mit einer WAV-Datei wird extrahiert und zugeschnitten; vorhandene Datei wird übersprungen; Serverfehler → `FetchError`, keine `.part`-Reste; ASAP-Dateien landen unter den Manifest-Pfaden. URLs sind als Modulkonstanten im Test überschreibbar.
   - Files: `testset/fetch.py`, `tests/test_testset_fetch.py`
   - Depends on: Step 2
6. **Lauf + Baseline + CLI** (TDD mit Fake-Backend): `transcribe_all` (Cache-Treffer, Überspringen ohne Audio, Fehler pro Stück), `baseline` (F1 bekannter Werte, keine Referenz, nicht transkribiert, Mittelwerte), CLI-Unterbefehle mit Exit-Codes.
   - Files: `testset/run.py`, `cli.py`, `tests/test_testset_run.py`, `tests/test_cli_testset.py`
   - Depends on: Steps 1–5
7. **Manifest befüllen + echter Download**: ASAP-Kandidaten aus `metadata.csv` (gepinnter Commit) eintragen, inkl. `start`/`end` und MAESTRO-Pfad. MAESTRO-Pfade der M1-Stücke eintragen (siehe Tabelle). Für Schubert op. 90/4 die Fassung wählen, deren F1 nach Schritt 9 die M1-Werte reproduziert (roh 0,988 / bereinigt 0,988). Ist das keine, die kürzeste Fassung (113 s) nehmen und die Abweichung zu M1 dokumentieren. Ivanov-Eintrag (Datei nach `internet/` verschieben). `testset fetch` real ausführen, dann `check`. **Versatz prüfen:** ASAP-Performance-MIDI gegen das zugeschnittene Audio. Kontrolle über die MAESTRO-MIDI desselben Bereichs: Onsets − `start` müssen mit der ASAP-MIDI übereinstimmen (±10 ms). Sonst Korrektur in `fetch` (Referenz-MIDI verschieben oder Audio anders schneiden) und dokumentieren.
   - Files: `testset/manifest.yaml`, `testset/README.md`
   - Depends on: Step 5
8. **Eigene Aufnahmen**: Der User liefert ≥ 1 Pop-, Jazz- und Impro-Aufnahme (Handy/Internet) mit Lizenz-/Herkunftsangabe. Einträge ohne `fetch`. Bis dahin meldet `check` sie als fehlend. Das Akzeptanzkriterium „≥ 1 je Stil“ ist erst danach erfüllt.
   - Files: `testset/manifest.yaml`
   - Depends on: Step 7 (User-Input)
9. **Transkription + Baseline real**: `testset transcribe` (~40–60 min CPU, im Hintergrund), dann `testset baseline`. Ergebnis-Tabelle in diesen Plan (Umsetzungsstand) übernehmen. Slow-Test `test_testset_real.py`: `check` ohne Fehler, F1 der ASAP- und MAESTRO-Stücke ≥ 0,90 (fängt Versatzfehler ab).
   - Files: `tests/integration/test_testset_real.py`, dieser Plan
   - Depends on: Steps 6–8
10. **Doku + Abschluss**: README-Abschnitt „Testset“, Status in Spec, Plan und Roadmap. `ruff`, `pytest`, `pytest -m slow`.
    - Files: `README.md`, `docs/roadmap.md`, `docs/features/testset.md`, dieser Plan
    - Depends on: Step 9

## Test Strategy
- **Unit** (schnell, ohne Netz, ohne Modelle): Manifest-Validierung, Dateiprüfung mit synthetischen Dateien, `RangeFile` und Zip-Extraktion gegen `http.server` auf `127.0.0.1` (Thread-Fixture, eigene Range-Behandlung), Zuschnitt, `cached_transcription`, `transcribe_all`/`baseline` mit Fake-Backend, CLI-Exit-Codes und -Ausgabe via `CliRunner`, F1-Hilfsfunktionen.
- **Integration** (`pytest -m slow`, Skip ohne Daten): echtes Testset → `check` fehlerfrei; Baseline-F1 ≥ 0,90 für Stücke mit Studio-Referenz; bestehender `test_accuracy.py` läuft weiter.
- **Manuell**: `testset fetch` im frischen Checkout (Netz), Abbruch mitten im Download und Fortsetzen, `testset transcribe` abbrechen und neu starten (fertige Stücke aus dem Cache).
- **Zuordnung der Akzeptanzkriterien**:
  - check OK / Exit 0 → `test_cli_testset` + slow
  - fehlende Datei / Pflichtfeld → `test_testset_manifest` + `test_testset_check` + `test_cli_testset`
  - frisches Checkout + fetch → manuell + `test_testset_fetch`
  - Cache teilweise → `test_testset_run`
  - Baseline ohne Modelllauf → `test_testset_run` (Backend-Aufrufe = 0)
  - Zusammensetzung → Unit-Test auf dem echten `manifest.yaml` (Anzahl 12–15, jeder Stil, jede Qualität; erst nach Schritt 8 grün)
  - M1-Test → `test_accuracy`

## Risks & Open Questions
- **Versatz ASAP-MIDI ↔ MAESTRO-Audio**: Die `start`/`end`-Semantik ist nicht vollständig dokumentiert (bei manchen Zeilen fehlt `start` oder `end`). Gegenmittel: Kontrolle in Schritt 7 und F1-Schwelle im Slow-Test.
- **Zip-Zugriff per Range**: Python-`zipfile` liest Zip64 korrekt, aber viele kleine Reads wären langsam → `BufferedReader` mit großem Puffer. Ein MAESTRO-WAV ist 50–150 MB, Download-Zeit hängt vom Netz ab.
- **Laufzeit `transcribe`**: ≈ 1× Echtzeit → ~40–60 min für das ganze Set. Läuft einmal im Hintergrund, danach Cache.
- **Lizenzen**: MAESTRO und ASAP CC BY-NC-SA 4.0 (Hobby, nicht kommerziell → ok, im Manifest vermerkt). Internet-Mitschnitte bleiben lokal, `fetch` lädt sie nicht.
- **Cache-Schlüssel = Datei-Hash**: Zuschnitt und FLAC-Kodierung müssen deterministisch sein (gleiche Version von `soundfile`/libsndfile), sonst werden neu geladene Dateien neu transkribiert. Akzeptabel; im README erwähnen.
- [ ] Eigene Pop-/Jazz-/Impro-Aufnahmen: liefert der User (Schritt 8). Bis dahin ist das Kriterium „≥ 1 je Stil“ offen.
- [ ] Schubert op. 90/4: Die genaue M1-Fassung ist unbekannt (5 Kandidaten im Test-Split). Sie wird über die F1-Werte aus M1 wiedergefunden (Schritt 7/9), sonst gilt die dokumentierte Abweichung.
