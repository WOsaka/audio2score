---
title: "Testset"
status: approved       # draft | approved | implemented
created: 2026-10-12
updated: 2026-10-12
---

# Feature: Testset (M2)

## Problem Statement
Ab M3 wird Teil B (Rhythmus, Harmonie, Partitur) entwickelt. Ohne feste Sammlung von Stücken mit Referenzen lässt sich Fortschritt dort nicht messen. Auch Teil A ist bisher nur auf drei MAESTRO-Stücken in Studioqualität geprüft. Handy-Aufnahmen, Internet-Mitschnitte sowie die Stile Pop, Jazz und Improvisation sind nicht abgedeckt. Betroffen ist der Entwickler (Hobbyprojekt), der jede Änderung gegen dieselbe Datenbasis prüfen will.

Zweck, nach Priorität:
1. Messbasis für Teil B (M3–M6): Performance-MIDI + Referenz-MusicXML (ASAP).
2. Teil A unter realen Bedingungen (Handy, Internet).
3. Grundlage für `audio2score eval` (M7).

## Goals
- [ ] Manifest mit 12–15 Stücken aller Stile (Klassik, Pop, Jazz, Improvisation), zusammen ≤ 60 min Audio
- [ ] ASAP-Ausschnitt (~6 Stücke mit MAESTRO-Audio, Performance-MIDI und Referenz-MusicXML) automatisch ladbar
- [ ] `audio2score testset check` prüft alle Einträge auf Vollständigkeit und Lesbarkeit
- [ ] `audio2score testset transcribe` legt Teil-A-Ergebnisse aller Audio-Stücke im Cache ab (fortsetzbar)
- [ ] `audio2score testset baseline` gibt die Note-F1 für Teil A pro Stück und Kategorie aus (wo es eine Referenz gibt)

## Out of Scope
- Partitur-Metrik für Teil B (M7)
- CLI-Befehl `eval` und Versionsvergleich (M7)
- Audio-/MIDI-/MusicXML-Daten im Repo (nur das Manifest wird eingecheckt)
- Kalibrierung der Cleanup-Schwellen (eigener Schritt nach M2)
- YouTube-Import oder anderer automatischer Download von Internet-Mitschnitten

## Zusammensetzung (Vorschlag)

| Gruppe | Anzahl | Inhalt | Referenz | Qualität |
|---|---|---|---|---|
| ASAP | ~6 | verschiedene Komponisten und Taktarten (z. B. Bach, Mozart, Beethoven, Chopin, Schumann, Debussy), Ausschnitte mit MAESTRO-Audio | Performance-MIDI + MusicXML | studio |
| MAESTRO (aus M1) | 3 | Chopin Op. 10/9, Scarlatti K. 525, Schubert Op. 90/4 | MIDI | studio |
| Internet | 1 | Ivanov, Nocturne Op. 9/3 (vorhanden) | keine | internet |
| Eigene / Internet | ≥ 3 | je ≥ 1 Pop, Jazz, Improvisation | meist keine | handy / internet |

## Manifest-Format
Eingecheckte YAML-Datei (Ort wird im Implementierungsplan festgelegt, z. B. `testset/manifest.yaml`). Pfade sind relativ zu `data/testset/`. Ein Eintrag:

```yaml
- id: asap-chopin-etude-10-1        # eindeutig, kebab-case
  style: classical                  # classical | pop | jazz | free
  source: asap                      # asap | maestro | own | internet
  quality: studio                   # studio | phone | internet
  audio: asap/chopin-etude-10-1.wav # optional (ASAP ohne Audio möglich)
  ref_midi: asap/chopin-etude-10-1.mid        # optional
  ref_musicxml: asap/chopin-etude-10-1.musicxml  # optional
  time_sig: 4/4                     # optional, Hinweis für Teil B
  tempo_hint: 120                   # optional
  license: CC BY-NC-SA 4.0          # Herkunft/Lizenz
  origin: "ASAP / MAESTRO v3, 2018 …"
  notes: ""                         # optional
```

Pflichtfelder: `id`, `style`, `source`, `quality`, `license`, `origin` sowie mindestens eines von `audio` / `ref_midi`.

## User Journey
1. Der User führt das Download-Skript bzw. den Befehl aus. ASAP-Auswahl und MAESTRO-Teile (per HTTP-Range wie in M1) landen in `data/testset/`.
2. Eigene und Internet-Aufnahmen legt der User von Hand in `data/testset/<gruppe>/` ab und trägt sie ins Manifest ein.
3. `audio2score testset check` meldet pro Eintrag OK, Warnung oder Fehler sowie eine Zusammenfassung.
4. `audio2score testset transcribe` transkribiert alle Audio-Einträge mit dem Standard-Backend. Bereits gecachte Stücke werden übersprungen, der Fortschritt wird angezeigt.
5. `audio2score testset baseline` gibt eine Tabelle aus: Stück, Kategorie (Stil, Qualität), Precision/Recall/F1 (Onset ±50 ms, Offsets ignoriert) sowie Mittelwerte pro Kategorie. Stücke ohne Referenz erscheinen als „keine Referenz“.

## Acceptance Criteria
- [ ] Given ein vollständig geladenes Testset, when `testset check` läuft, then sind alle Einträge OK und der Exit-Code ist 0.
- [ ] Given ein Eintrag mit fehlender Datei oder fehlendem Pflichtfeld, when `testset check` läuft, then wird der Eintrag mit Grund gemeldet und der Exit-Code ist ≠ 0.
- [ ] Given ein frisches Checkout ohne Daten, when das Download-Skript läuft, then liegen alle ASAP- und MAESTRO-Einträge des Manifests vor und `check` meldet für sie OK.
- [ ] Given teilweise gefüllter Cache, when `testset transcribe` läuft, then werden nur die fehlenden Stücke transkribiert.
- [ ] Given gecachte Teil-A-Ergebnisse, when `testset baseline` läuft, then erscheint die F1 für jedes Stück mit Referenz-MIDI, dazu Mittelwerte pro Stil und Qualität, ohne erneuten Modelllauf.
- [ ] Das Manifest enthält 12–15 Stücke, davon ≥ 1 je Stil (classical, pop, jazz, free) und ≥ 1 je Qualität (studio, phone/internet).
- [ ] Der bestehende Genauigkeitstest aus M1 (`data/testset/maestro/`) läuft weiter.

## Edge Cases & Error States
| Scenario | Expected Behavior |
|----------|-------------------|
| Datei aus dem Manifest fehlt | `check`: Fehler für den Eintrag; `transcribe`/`baseline`: Warnung, Stück übersprungen |
| Eintrag ohne Referenz | kein F1, Anzeige „keine Referenz“; Transkription läuft trotzdem |
| Eintrag nur mit MIDI, ohne Audio (ASAP) | kein Teil A, gilt als direkte Teil-B-Eingabe; in `transcribe` übersprungen |
| Datei nicht lesbar (defektes Audio/MIDI/MusicXML) | `check`: Fehler mit Dateipfad und Ursache |
| Download scheitert (Netz, URL geändert) | klare Meldung, welches Stück fehlt; bereits geladene bleiben erhalten; erneuter Lauf setzt fort |
| Doppelte `id` im Manifest | `check`: Fehler |
| Unbekannter Wert bei `style`/`source`/`quality` | `check`: Fehler mit erlaubten Werten |
| Abbruch während `transcribe` | fertige Stücke sind gecacht, Neustart setzt fort |

## Technical Constraints
- Performance: `check` in Sekunden. `transcribe` ~Echtzeit auf der CPU (≤ 60 min Audio gesamt), zeigt Fortschritt und lässt sich fortsetzen. `baseline` nur aus dem Cache, ohne Modelllauf.
- Security: Downloads nur von festen Quellen (ASAP-GitHub, MAESTRO-Server); keine Ausführung geladener Inhalte.
- Compliance: Lizenz und Herkunft je Eintrag im Manifest. Daten werden nicht eingecheckt, Internet-Mitschnitte bleiben lokal.

## Dependencies
- M0+M1 `transcribe-audio-to-midi`: Backends, Cache, NoteList, MIDI-Laden
- ASAP-Datensatz (GitHub `fosfrancesco/asap-dataset`): MusicXML, Performance-MIDI, Verknüpfung zu MAESTRO
- MAESTRO v3: Audio, Teilladung per HTTP-Range wie in M1
- Pakete: `pyyaml` (neu), `mir_eval` als Laufzeit-Abhängigkeit statt nur dev

## Open Questions
- [ ] Konkrete Pop-, Jazz- und Impro-Aufnahmen (liefert der User). Gibt es für einige davon Referenzen (Noten/MIDI)?
- [ ] Endgültige ASAP-Auswahl: Kriterien sind Stil-/Taktart-Vielfalt, vorhandenes MAESTRO-Audio und Länge (ggf. Ausschnitte).
- [ ] Ablageort des Manifests (`testset/manifest.yaml` vs. `data/testset/manifest.yaml` mit Ausnahme in `.gitignore`)
