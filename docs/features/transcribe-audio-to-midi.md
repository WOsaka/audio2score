---
title: "Transcribe Audio to MIDI"
status: approved        # draft | approved | implemented
created: 2026-10-11
updated: 2026-10-11
---

# Feature: Transcribe Audio to MIDI

Meilenstein M0+M1 aus `docs/roadmap.md` (Teil A der Pipeline).

## Problem Statement
Eine Klavieraufnahme (eigene Aufnahme oder Internet-Mitschnitt) soll in Noten-Events (Tonhöhe, Beginn, Ende, Lautstärke, Pedal) umgewandelt werden. Das ist die Grundlage aller weiteren Schritte (Partitur, Lead Sheet). Da nur eine CPU zur Verfügung steht, ist die Transkription langsam und ihr Ergebnis muss wiederverwendbar sein.

## Goals
- [ ] Installierbares Python-Paket `audio2score` mit CLI (`pip install -e .[dev]`, läuft unter Windows mit CPU-Torch)
- [ ] Gängige Audioformate (wav, mp3, m4a, flac, webm) laden und vorverarbeiten (Mono, 16 kHz, Normalisierung)
- [ ] Transkription mit austauschbaren Backends: ByteDance (Standard, im Basispaket) und Basic Pitch (optionales Extra `.[basic-pitch]`)
- [ ] Internes Datenmodell `NoteList` (Noten + Pedal-Events), als JSON serialisierbar
- [ ] Cache im Projektordner `cache/`: gleiche Datei + gleiches Backend wird nicht erneut transkribiert; Ort änderbar über `--cache-dir` bzw. Umgebungsvariable `AUDIO2SCORE_CACHE`
- [ ] Aufräumen: zu kurze/leise Noten und Oktav-Geisternoten entfernen (abschaltbar)
- [ ] MIDI-Export (Performance-Timing, inkl. Sustain-Pedal als CC64)
- [ ] CLI-Befehl `audio2score transcribe <audio> -o <datei.mid> [--backend] [--cache-dir] [--no-cache] [--no-cleanup]`

## Out of Scope
- Beat-Tracking, Quantisierung, MusicXML, PDF, Lead Sheet (spätere Features)
- Quellentrennung (Demucs), YouTube-Download
- Eigenes Modelltraining, GPU-Optimierung
- Web-Oberfläche

## User Journey
1. Nutzer ruft `audio2score transcribe aufnahme.mp3 -o out/aufnahme.mid` auf.
2. System lädt und normalisiert das Audio, zeigt Dauer und gewähltes Backend.
3. Beim ersten Lauf werden ggf. Modellgewichte heruntergeladen (mit Hinweis), dann läuft die Transkription mit Fortschrittsanzeige.
4. System speichert das Ergebnis im Cache und schreibt die MIDI-Datei; Ausgabe: Anzahl Noten, Tonumfang, Laufzeit.
5. Ein zweiter Aufruf mit derselben Datei liefert das Ergebnis sofort aus dem Cache.
6. Nutzer öffnet die MIDI-Datei z. B. in MuseScore zur Kontrolle.

## Acceptance Criteria
- [ ] Given eine saubere Klavieraufnahme (wav/mp3), when `transcribe` läuft, then entsteht eine abspielbare MIDI-Datei, deren Noten hörbar dem Original entsprechen.
- [ ] Given ein MAESTRO-Ausschnitt mit Referenz-MIDI, when mit ByteDance transkribiert, then ist die Note-F1 (Onset ±50 ms, mir_eval) ≥ 0,90.
- [ ] Given dieselbe Datei und dasselbe Backend, when erneut aufgerufen, then wird der Cache genutzt (keine Modellausführung, < 2 s).
- [ ] Given `--backend basic-pitch` und installiertes Extra, when aufgerufen, then wird Basic Pitch verwendet und separat gecacht.
- [ ] Given `--backend basic-pitch` ohne installiertes Extra, when aufgerufen, then erscheint ein Hinweis auf `pip install -e .[basic-pitch]` (Exit-Code ≠ 0).
- [ ] Given `--cache-dir` oder `AUDIO2SCORE_CACHE`, when aufgerufen, then wird dieser Ort statt `cache/` verwendet (Option hat Vorrang vor Umgebungsvariable).
- [ ] Given die Ausgabe-MIDI, when untersucht, then enthält sie Sustain-Pedal-Events (CC64), sofern das Backend Pedal liefert.
- [ ] Given `--no-cleanup`, when aufgerufen, then werden die Roh-Noten unverändert exportiert.
- [ ] Die `NoteList` lässt sich verlustfrei nach JSON und zurück serialisieren (Unit-Test).

## Edge Cases & Error States
| Scenario | Expected Behavior |
|----------|-------------------|
| Datei existiert nicht / Format nicht lesbar | Klare Fehlermeldung, Exit-Code ≠ 0 |
| ffmpeg fehlt (für mp3/m4a/webm) | Fehlermeldung mit Installationshinweis; wav/flac funktionieren trotzdem |
| Modellgewichte nicht herunterladbar (offline) | Fehlermeldung mit Hinweis, Pfad zu manuell abgelegten Gewichten über Option/Umgebungsvariable |
| Sehr lange Aufnahme (> 15 min) | Funktioniert (Backend segmentiert intern), Fortschrittsanzeige |
| Stille / kein Klavier erkannt | Leere MIDI-Datei + Warnung, kein Absturz |
| Stereo, andere Samplerate, Clipping | Wird in der Vorverarbeitung vereinheitlicht |
| Cache-Datei beschädigt oder alte Version | Wird verworfen und neu berechnet |

## Technical Constraints
- Performance: CPU-only; Transkription etwa Echtzeit oder schneller ist akzeptabel. Cache-Treffer < 2 s.
- Security: keine (lokales Tool). Gewichte nur aus offiziellen Quellen laden.
- Compliance: Lizenzen der Modellgewichte im README vermerken; Hobbyprojekt, keine Weitergabe von Audio.

## Dependencies
- Python 3.12
- Basispaket: `torch` (CPU), `piano_transcription_inference`, `librosa`, `soundfile`, `pretty_midi`, `typer`
- Extra `basic-pitch`: `basic-pitch`
- Extra `dev`: `pytest`, `ruff`, `mir_eval`
- Extern: ffmpeg

## Open Questions
- [x] Basic Pitch → optionales Extra `.[basic-pitch]`, damit das Basispaket schlank bleibt.
- [x] Cache-Ort → Projektordner `cache/`, änderbar über `--cache-dir` / `AUDIO2SCORE_CACHE`.
- [x] Python-Version → 3.12. In der Implementierungsplanung die 3.12-Kompatibilität aller Abhängigkeiten unter Windows verifizieren (insb. `basic-pitch` und dessen ONNX/TF-Abhängigkeiten); bei Inkompatibilität des Extras dokumentieren statt auf 3.11 zu wechseln.
