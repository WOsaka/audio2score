---
title: "Roadmap audio2score"
created: 2026-10-11
updated: 2026-10-12
---

# Roadmap audio2score

## Rahmenbedingungen

| Entscheidung | Folge |
|---|---|
| Hobby-/Lernprojekt | Pragmatische Werkzeugwahl; eigene Algorithmen vor allem in Teil B (dort lernt man am meisten). Lizenzen der Modelle nur zur Kenntnis nehmen. |
| Erst CLI, später Web | Bibliothek + dünne CLI; Web nutzt später dieselben Funktionen. |
| Alle Stile (Klassik, Pop, Jazz, Improvisation) | Stil-Presets für die Quantisierung (`classical`, `pop`, `jazz`, `free`). |
| Gemischte Aufnahmen / Internet | Robuste Vorverarbeitung; optional Quellentrennung (Demucs). |
| Ausgabe: MusicXML, MIDI, PDF, Lead Sheet | Internes Partitur-Modell, mehrere Exporter; Lead Sheet als eigener Zweig. |
| Nur CPU | Teil A langsam (~Echtzeit) → Cache; kein eigenes Training. |

## Architektur

```
Audio (wav/mp3/m4a/webm)
  → audio/      Laden (ffmpeg), Mono, 16 kHz, Normalisierung, opt. Demucs
  → transcribe/ Backend (ByteDance | Basic Pitch) → NoteList (+ Pedal)   [Cache]
  → cleanup/    Geisternoten, Mindestdauer, Pedal-Behandlung
  ── Teil B (startet auch direkt mit MIDI) ──
  → rhythm/     Beats/Downbeats (beat_this), Taktart, Quantisierung, Swing
  → harmony/    Tonart, Pitch Spelling, Akkorde
  → score/      Handtrennung, Stimmen, music21-Score, Lead Sheet
  → export/     MusicXML, MIDI (roh + quantisiert), PDF (MuseScore / LilyPond)
  → eval/       Note-F1 (mir_eval), Partitur-Metrik
```

### Geplante CLI

```bash
audio2score run aufnahme.mp3 -o out/ --formats musicxml,midi,pdf --style pop --leadsheet
audio2score transcribe aufnahme.mp3 -o out/notes.mid --backend bytedance   # nur Teil A
audio2score score out/notes.mid -o out/ --style classical --tempo-hint 72 --time-sig 3/4  # nur Teil B
audio2score eval data/testset/
```

## Meilensteine → Features

Jeder Meilenstein wird ein Feature im Workflow `/feature:spec` → `/feature:implementation-plan` → `/feature:code`.

| # | Feature (`docs/features/…`) | Inhalt | Status |
|---|---|---|---|
| M0+M1 | `transcribe-audio-to-midi` | Projektgerüst, CPU-Setup, Audio laden, Backends ByteDance + Basic Pitch, NoteList-Modell, Cache, Aufräumen, MIDI-Export, CLI `transcribe` | implemented — Note-F1 0,97–0,99 auf MAESTRO, manuell abgenommen (Ivanov-Nocturne, 3 min in 330 s auf CPU) |
| M2 | `testset` | 10–15 Stücke aller Stile + ASAP-Ausschnitt (Performance-MIDI + Referenz-MusicXML), Manifest-Format | umgesetzt bis auf eigene Pop-/Jazz-/Impro-Aufnahmen (Platzhalter im Manifest); Baseline Note-F1 Ø 0,985 auf 9 Studiostücken |
| M3 | `rhythm-quantization-v1` | Beats/Downbeats, Taktart, binäre Quantisierung, naive Handtrennung, erstes MusicXML, CLI `score` | offen |
| M4 | `harmony-and-pdf` | Tonart, Pitch Spelling, PDF-Export über MuseScore, CLI `run` | offen |
| M5 | `readable-notation` | Triolen + Raster-Konsistenz (Viterbi über Beats), Stimmentrennung, Dauer-/Legato-Regeln, Stil-Presets, Swing | offen |
| M6 | `lead-sheet` | Melodie (Skyline + Glättung), Akkorderkennung (Templates + Wechselstrafe), Lead-Sheet-Export | offen |
| M7 | `evaluation` | CLI `eval`: Note-F1 für Teil A, Partitur-Metrik für Teil B, Vergleich zwischen Versionen | offen |
| M8 | `web-ui` | FastAPI, Upload, Hintergrund-Jobs mit Fortschritt, Verovio-Vorschau, Downloads | offen |
| opt. | – | Demucs, Handtrennung per DP, gelernte Quantisierung, YouTube-Import (nur privat) | – |

Nach M4 steht ein durchgängig brauchbares Werkzeug; danach verbessert jeder Meilenstein die Qualität messbar am Testset.

## Kernalgorithmen (Notizen für die Specs)

### Teil A
- ByteDance „High-resolution Piano Transcription“ (`piano_transcription_inference`) als Standard: Onset, Offset, Velocity, Pedal getrennt. Für die Notation Tasten-Offsets nutzen.
- Basic Pitch als schnelle Alternative.
- Cache-Schlüssel: Hash(Audio) + Backend + Version → JSON in `cache/`.
- Aufräumen: zu kurze/leise Noten relativ zur lokalen Lautheit; Oktav-Geisternoten (leise Note exakt eine Oktave über lauter, gleichzeitiger Note).

### Rhythmus
1. Beats + Downbeats mit `beat_this` (auf Audio; bei reinem MIDI: synthetisieren oder aus Onsets schätzen). `madmom` nur als Fallback (Installationsprobleme unter Windows).
2. Taktart: Modus der Beats pro Takt; 6/8 vs. 3/4 über Unterteilung.
3. Quantisierung pro Beat: Onset → Beat-Index + Bruchteil; Raster binär (0, ¼, ½, ¾) oder ternär (0, ⅓, ⅔); Kosten = Abweichung + Komplexität; Konsistenz zu Nachbar-Beats (später Viterbi).
4. Dauern: Offsets quantisieren, Legato bis zum nächsten Onset derselben Stimme bei kleiner Lücke, sonst Pause/Staccato.
5. Swing: Offbeat-Achtel konsistent bei ~0,6–0,7 → gerade notieren + „Swing“-Angabe.
6. Nutzerhinweise `--tempo-hint`, `--time-sig` lösen Mehrdeutigkeiten (v. a. bei Rubato).

### Harmonie
- Tonart: Krumhansl-Schmuckler (music21), später gefenstert.
- Pitch Spelling: zuerst tonartbasiert, später Line-of-Fifths (Temperley / PS13).
- Akkorde: Tonklassen pro Halbtakt/Takt, gewichtet nach Dauer/Velocity, Template-Matching (Dur, Moll, 7, maj7, m7, dim, sus…), Bass für Umkehrungen, Wechselstrafe.

### Partitur
- Handtrennung v1: Split am mittleren C mit Hysterese + Spannweitenlimit; v2: DP mit Sprung-/Spannweiten-/Kreuzungskosten.
- Stimmen: gleichzeitige Noten gleicher Dauer → Akkord; überlappende verschiedene Dauern → zweite Stimme.
- music21 `makeNotation` für Haltebögen, Balken, Pausen.
- PDF: `MuseScore4.exe -o out.pdf in.musicxml`, Fallback `musicxml2ly` + LilyPond.

## Abhängigkeiten

`torch` (CPU), `piano_transcription_inference`, `basic-pitch`, `beat_this`, `librosa`, `soundfile`, `pretty_midi`, `music21`, `mir_eval`, `typer`, `pytest`, `ruff`; extern ffmpeg, MuseScore 4; später `fastapi`, `verovio`.

## Risiken

- **Windows-Installation** (Torch, ffmpeg, Download der Modellgewichte) → im ersten Feature früh klären.
- **CPU-Laufzeit** → Cache, Teil B unabhängig entwickelbar.
- **Internet-Aufnahmen** (Kompression, Hall) → im Testset getrennt messen.
- **Rubato (Klassik)** bleibt am schwierigsten → Nutzerhinweise als wichtigster Hebel.
- **Erwartung**: Transkribiert wird eine *Aufführung*, nicht die Originalpartitur rekonstruiert; Triller/Verzierungen erscheinen als schnelle Notenfolgen.
