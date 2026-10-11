---
title: "Transcribe Audio to MIDI"
status: draft          # draft | approved | implemented
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
- [ ] Transkription mit austauschbaren Backends: ByteDance (Standard) und Basic Pitch
- [ ] Internes Datenmodell `NoteList` (Noten + Pedal-Events), als JSON serialisierbar
- [ ] Cache: gleiche Datei + gleiches Backend wird nicht erneut transkribiert
- [ ] Aufräumen: zu kurze/leise Noten und Oktav-Geisternoten entfernen (abschaltbar)
- [ ] MIDI-Export (Performance-Timing, inkl. Sustain-Pedal als CC64)
- [ ] CLI-Befehl `audio2score transcribe <audio> -o <datei.mid> [--backend] [--no-cache] [--no-cleanup]`

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
- [ ] Given `--backend basic-pitch`, when aufgerufen, then wird Basic Pitch verwendet und separat gecacht.
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
- Python 3.11, `torch` (CPU), `piano_transcription_inference`, `basic-pitch`, `librosa`, `soundfile`, `pretty_midi`, `typer`, `mir_eval` (Test), `pytest`, `ruff`
- Extern: ffmpeg

## Open Questions
- [ ] Basic Pitch zieht TensorFlow/ONNX-Abhängigkeiten nach — als optionales Extra (`.[basic-pitch]`) statt Pflicht?
- [ ] Cache-Ort: Projektordner `cache/` oder Benutzerverzeichnis (z. B. `%LOCALAPPDATA%\audio2score`)?
- [ ] Python 3.11 vs. 3.12 — abhängig von der Kompatibilität der Backends (in der Planung prüfen).
