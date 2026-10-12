# audio2score

Klavieraufnahme rein, Noten raus: automatische Transkription von Klavier-Audio zu MIDI, MusicXML, PDF und Lead Sheet.

```
Audio → Transkriptionsmodell → Noten-Events (MIDI)        ← Teil A
      → Beats/Takt → Quantisierung → Tonart/Spelling
      → Hände/Stimmen → Partitur (MusicXML, PDF, Lead Sheet) ← Teil B
```

Status: Teil A (`audio2score transcribe`) und der erste Durchstich durch Teil B (`audio2score score`: Takte, Taktart,
Notenwerte, zwei Systeme) sind umgesetzt, Tonart, PDF und Lead Sheet folgen — siehe [`docs/roadmap.md`](docs/roadmap.md).

## Voraussetzungen

- Python 3.12 (die Abhängigkeiten sind nur dafür getestet)
- Nur CPU nötig; eine GPU wird nicht verwendet
- ffmpeg ist für mp3/m4a u. Ä. nötig und wird über das Paket `imageio-ffmpeg` mitgeliefert; ein ffmpeg im `PATH` hat Vorrang
- MuseScore 4 zum Öffnen der MusicXML-Dateien (und später für den PDF-Export)

## Installation

```powershell
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
audio2score --version
```

Beim ersten Lauf lädt das ByteDance-Backend die Modellgewichte (ca. 165 MB, Zenodo) nach
`~/piano_transcription_inference_data/`. Ohne Netz die Datei `note_F1=0.9677_pedal_F1=0.9186.pth`
([Download](https://zenodo.org/record/4034264)) manuell dort ablegen, oder den Ort mit `--checkpoint` bzw.
`AUDIO2SCORE_CHECKPOINT` angeben.

Die Beat-Erkennung (`beat_this`, nur für `score`) lädt beim ersten Lauf ihre Gewichte (ca. 81 MB) nach
`~/.cache/torch/hub/checkpoints/`. `torchaudio` ist auf `2.11.0` festgelegt: Für `torch` 2.14 gibt es noch keine
passende Version, die Kombination ist getestet.

### Optional: Basic-Pitch-Backend

Basic Pitch verlangt unter Windows mit Python 3.12 ein TensorFlow ohne verfügbares Wheel. Das Paket enthält aber ein
ONNX-Modell, das nur `onnxruntime` braucht. Deshalb in zwei Schritten installieren:

```powershell
pip install -e .[basic-pitch]
pip install --no-deps basic-pitch==0.4.0
```

## Nutzung

```powershell
audio2score transcribe aufnahme.mp3 -o out\aufnahme.mid
audio2score transcribe aufnahme.mp3 -o out\aufnahme.mid --backend basic-pitch
```

| Option | Bedeutung |
|---|---|
| `-o, --output` | Ziel-MIDI-Datei (Pflicht; Ordner werden angelegt) |
| `--backend` | `bytedance` (Standard, mit Pedal) oder `basic-pitch` |
| `--cache-dir` | Cache-Ordner; sonst `AUDIO2SCORE_CACHE`, sonst `./cache` |
| `--no-cache` | Cache weder lesen noch schreiben |
| `--no-cleanup` | rohe Noten ohne Aufräumen exportieren |
| `--checkpoint` | Modellgewichte des ByteDance-Backends |

Der Cache enthält die **rohen** Noten pro Datei (Hash des Inhalts), Backend und Version. Ein zweiter Aufruf braucht
deshalb kein Modell mehr (< 2 s), und `--no-cleanup` oder geänderte Aufräumregeln wirken ohne neue Transkription.
Auf der CPU dauert die erste Transkription etwa so lange wie die Aufnahme selbst (ByteDance).

Das Aufräumen entfernt zu kurze (< 30 ms) und zu leise Noten sowie leise Oktav-Geisternoten. Die MIDI-Datei enthält
Tasten-Offsets (nicht pedal-verlängert) und das Sustain-Pedal als CC64.

## Partitur erzeugen

```powershell
audio2score score aufnahme.mp3 -o out\
audio2score score aufnahme.mp3 -o out\ --time-sig 3/4
```

Das erzeugt im Zielordner `aufnahme.musicxml` (zwei Systeme, Takte, Taktart, Tempo), `aufnahme.quantized.mid`
(Noten auf dem Raster, mit der Tempo-Map der erkannten Beats – läuft synchron zur Aufnahme) und `aufnahme.beats.json`
(Beat-Raster mit Takt- und Zählzeitnummer). Noten und Beats kommen aus dem Cache; fehlen sie, werden sie berechnet.
Danach dauert ein neuer Aufruf (z. B. mit anderer `--time-sig`) nur Sekunden.

| Option | Bedeutung |
|---|---|
| `-o, --output` | Zielordner (Pflicht; wird angelegt) |
| `--time-sig` | `2/4`, `3/4`, `4/4`, `3/8`, `6/8`, `9/8`, `12/8`; sonst automatisch (nur n/4) |
| `--backend`, `--cache-dir`, `--no-cache`, `--checkpoint` | wie bei `transcribe` |

Grenzen von v1: binäres Sechzehntel-Raster (keine Triolen, kein Swing), eine Stimme pro Hand, Handtrennung am
mittleren C, eine Taktart pro Stück, keine Tonart (Vorzeichen als ♯/♭ je Note). Bei starkem Rubato oder halbem/doppeltem
Tempo der Beat-Erkennung entstehen lesbare, aber unpassende Takte; dann hilft `--time-sig` oder gar nichts.
Die Beat-Erkennung `beat_this` steht samt Gewichten unter MIT-Lizenz.

## Testset

Feste Sammlung von 12 Stücken mit Referenzen (Manifest: `testset/manifest.yaml`, Details:
`testset/README.md`). Die Daten liegen unter `data/testset/` und sind nicht eingecheckt.

```powershell
audio2score testset fetch        # ASAP- und MAESTRO-Stücke laden (fortsetzbar)
audio2score testset check        # Vollständigkeit und Lesbarkeit prüfen
audio2score testset transcribe   # Teil A in den Cache (fortsetzbar, ~Echtzeit auf der CPU)
audio2score testset baseline     # Note-F1 pro Stück, Mittel pro Stil/Qualität, ohne Modelllauf
audio2score testset score -o out\testset   # Partituren für alle Stücke (Noten nur aus dem Cache), Taktart/Takte ist/soll
```

## Tests

```powershell
pytest                 # schnell, ohne Modelle und Netz
pytest -m slow         # echte Modelle auf einem kurzen Clip, Cache-Zeit, Genauigkeit
ruff check . ; ruff format .
```

Der Genauigkeitstest (Note-F1 ≥ 0,90) erwartet MAESTRO-Paare `name.wav` + `name.midi` in
`data/testset/maestro/` (laden mit `audio2score testset fetch`) und wird sonst übersprungen.
`tests/integration/test_testset_real.py` prüft das ganze Testset.

## Lizenzen

- ByteDance `piano_transcription_inference`: Code MIT; für die Modellgewichte gilt die Lizenz auf der
  [Zenodo-Seite](https://zenodo.org/record/4034264).
- Basic Pitch (Spotify): Apache-2.0.
- `beat_this` (CPJKU): Code und Gewichte MIT.
- music21: BSD.

Entwicklungsablauf und Konventionen: siehe `CLAUDE.md`.
