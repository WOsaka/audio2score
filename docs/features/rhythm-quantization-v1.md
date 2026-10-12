---
title: "Rhythmus-Quantisierung v1"
status: approved        # draft | approved | implemented
created: 2026-10-12
updated: 2026-10-12
---

# Feature: Rhythmus-Quantisierung v1 (M3)

## Problem Statement
Teil A liefert Noten-Events in Sekunden (Performance-MIDI), ohne Takte, Notenwerte oder Systeme. Daraus lässt sich nicht spielen. M3 ist der erste Durchstich durch Teil B: Aus einer Aufnahme entsteht eine lesbare Partitur mit Takten, Taktart, Notenwerten und zwei Systemen als MusicXML. Betroffen ist der Entwickler/Nutzer (Hobbyprojekt), der bisher nur MIDI bekommt.

Die Qualität ist bewusst „v1“: binäres Raster, eine Stimme pro Hand, naive Handtrennung. Lesbarkeit verbessern M4–M6.

## Goals
- [ ] `audio2score score <audio> -o <ordner>` erzeugt MusicXML, quantisiertes MIDI und eine Beat-Datei
- [ ] Beats und Downbeats mit `beat_this` aus dem Audio, im Cache abgelegt
- [ ] Taktart automatisch (2/4, 3/4, 4/4) oder per `--time-sig`
- [ ] Binäre Quantisierung auf Sechzehntel, Auftakt als unvollständiger erster Takt
- [ ] Naive Handtrennung in zwei Systeme (Violin-/Bassschlüssel)
- [ ] `audio2score testset score` erzeugt die Ausgaben für alle Testset-Stücke und prüft ihre Lesbarkeit
- [ ] Quantisierung, Handtrennung und Export sind ohne Modelllauf entwickel- und testbar (nur aus dem Cache)

## Out of Scope
- Triolen, ternäre Raster, Swing (M5)
- Automatische Erkennung von 6/8 und anderen zusammengesetzten Taktarten (nur per `--time-sig`)
- Taktartwechsel im Stück, Tempowechsel in der Partitur
- Stimmentrennung innerhalb einer Hand (M5)
- Tonart und Pitch Spelling (M4) — Vorzeichen bleiben naiv (Kreuze, keine Tonartvorzeichnung)
- PDF-Export, CLI `run` (M4)
- Stil-Presets, `--tempo-hint`
- Viterbi-Konsistenz über Beats (M5), Handtrennung per DP (optional)
- Reiner MIDI-Eingang ohne Audio (Beats aus Onsets schätzen)
- Automatische Partitur-Metrik, Beat-F1 (M7)
- Pedalzeichen in der Partitur

## Verarbeitung (fachlich)

1. **Noten**: aus dem Teil-A-Cache (bei Fehltreffer wird transkribiert), nach dem Aufräumen. Dauern aus Tasten-Offsets, nicht pedal-verlängert.
2. **Beats/Downbeats**: `beat_this` auf dem Audio. Ergebnis im Cache (Schlüssel: Audio-Hash + Modell/Version), getrennt vom Noten-Cache.
3. **Taktart**: Modus der Beats pro Takt aus den erkannten Downbeats, beschränkt auf 2/4, 3/4, 4/4. `--time-sig` überschreibt. Eine Taktart für das ganze Stück.
4. **Taktraster**: Die Downbeats bestimmen nur Taktart und Phase (häufigste Position des Taktanfangs). Danach wird ab dem ersten Taktanfang fest durchgezählt; einzelne abweichende Downbeats verschieben keine Takte.
5. **Auftakt**: Beats vor dem ersten Taktanfang bilden einen unvollständigen ersten Takt. Vor dem ersten und nach dem letzten erkannten Beat wird das Beat-Raster mit dem lokalen Tempo fortgesetzt, sodass jede Note eine Position bekommt.
6. **Quantisierung**: Onset → Beat-Index + Bruchteil (linear zwischen zwei Beats), gerundet auf Sechzehntel (0, ¼, ½, ¾ des Viertel-Beats). Offsets ebenso, Mindestdauer ein Sechzehntel.
7. **Handtrennung**: Split am mittleren C mit Hysterese und Spannweitenlimit (Roadmap, v1).
8. **Eine Stimme pro Hand**: Noten mit gleichem quantisiertem Onset in einer Hand werden ein Akkord mit gemeinsamer Dauer. Eine Dauer endet spätestens am nächsten Onset derselben Hand. Noten gleicher Tonhöhe, die auf dieselbe Position fallen, werden zusammengelegt.
9. **Partitur**: music21-Score mit zwei Systemen, Taktart, einer Metronomangabe (Median der Beat-Abstände); Haltebögen, Balken und Pausen über `makeNotation`.
10. **Export**:
    - `<name>.musicxml` — die Partitur
    - `<name>.quantized.mid` — Noten auf dem Raster, mit der Tempo-Map der erkannten Beats (läuft synchron zur Aufnahme)
    - `<name>.beats.json` — Beat-Zeiten, Downbeat-Markierung, Taktart, Median-Tempo

## User Journey
1. Der User ruft `audio2score score aufnahme.mp3 -o out/` auf (optional `--time-sig 3/4`, `--backend`, `--cache-dir`, `--no-cache` wie bei `transcribe`).
2. Noten kommen aus dem Cache; fehlen sie, wird transkribiert (mit Fortschrittsmeldung wie bei `transcribe`).
3. Beats kommen aus dem Cache; fehlen sie, läuft `beat_this` (Meldung „Erkenne Beats ...“).
4. Das Programm gibt eine Zusammenfassung aus: Taktart (erkannt oder vorgegeben), Tempo, Anzahl Takte, Auftakt ja/nein, Noten pro Hand, Laufzeit, Pfade der drei Dateien.
5. Der User öffnet `out/aufnahme.musicxml` in MuseScore und hört bei Bedarf `out/aufnahme.quantized.mid` gegen die Aufnahme.
6. Stimmt die Taktart nicht, wiederholt der User den Aufruf mit `--time-sig`; das läuft ohne Modelllauf in Sekunden.
7. `audio2score testset score -o out/testset/` verarbeitet alle Audio-Stücke des Manifests (nur aus dem Cache), liest jedes MusicXML zur Kontrolle wieder ein und gibt pro Stück erkannte Taktart, Taktzahl und – wo im Manifest bzw. in der Referenz vorhanden – die Soll-Werte aus.

## Acceptance Criteria
- [ ] Given eine Audiodatei mit gecachten Noten und Beats, when `score` läuft, then entstehen `.musicxml`, `.quantized.mid` und `.beats.json` im Zielordner, ohne Modelllauf.
- [ ] Given eine Audiodatei ohne Cache-Einträge, when `score` läuft, then werden Noten und Beats berechnet, gecacht und dieselben drei Dateien geschrieben.
- [ ] Das MusicXML hat zwei Systeme (Violin-/Bassschlüssel), eine Taktart und eine Metronomangabe; jeder Takt außer Auftakt und letztem Takt ist vollständig gefüllt.
- [ ] Jedes erzeugte MusicXML lässt sich mit music21 wieder einlesen; MuseScore 4 öffnet es ohne Fehlermeldung (manuell an 2–3 Stücken).
- [ ] Given `--time-sig 3/4`, when `score` läuft, then steht 3/4 in der Partitur, unabhängig von der Erkennung.
- [ ] Given ein synthetisches Stück mit bekanntem Raster (Noten exakt auf Sechzehnteln, feste Beats), when quantisiert wird, then stimmen Positionen, Dauern und Taktzahl exakt.
- [ ] Given Noten vor dem ersten Taktanfang, when die Partitur entsteht, then ist der erste Takt ein Auftakt mit passender Länge.
- [ ] Given das transkribierte Testset, when `testset score` läuft, then entsteht für alle 12 Stücke ein einlesbares MusicXML und der Exit-Code ist 0.
- [ ] Bei den metrisch stabilen Stücken (Pop, einfache Klassik) stimmt die erkannte Taktart mit der Referenz; die Taktzahl weicht höchstens geringfügig ab (Richtwert, kein automatischer Test).
- [ ] Manuelle Abnahme an 2–3 Stücken: erkennbar das Stück, vom Blatt nachspielbar.
- [ ] Das quantisierte MIDI läuft hörbar synchron zur Aufnahme.
- [ ] Tests für Quantisierung, Handtrennung und Export laufen ohne Modelllauf und ohne Netz.

## Edge Cases & Error States
| Scenario | Expected Behavior |
|----------|-------------------|
| Audiodatei fehlt oder ist nicht lesbar | Fehlermeldung wie bei `transcribe`, Exit-Code 1 |
| `beat_this` nicht installiert / Gewichte nicht ladbar | klare Meldung mit Installationshinweis, Exit-Code 1 |
| Keine Noten erkannt | Fehlermeldung „keine Noten“, keine Dateien, Exit-Code 1 |
| Keine oder zu wenige Beats erkannt (sehr kurz, frei gespielt) | Fehlermeldung mit Hinweis auf `--time-sig`; ohne Beats keine Partitur, Exit-Code 1 |
| Keine Downbeats erkannt, aber Beats | Taktart 4/4 angenommen (oder `--time-sig`), Takt beginnt am ersten Beat, Warnung |
| Uneinheitliche Beats pro Takt | Modus gewinnt; Warnung mit Anteil der abweichenden Takte |
| Ungültiger Wert bei `--time-sig` | Abbruch mit den erlaubten Werten |
| `--time-sig 6/8` | Beats werden als punktierte Viertel gedeutet und in sechs Sechzehntel geteilt; ohne automatische Erkennung |
| Noten vor dem ersten / nach dem letzten Beat | Beat-Raster wird mit lokalem Tempo fortgesetzt |
| Schnelle Figuren (Triller, 32stel) | fallen auf dieselbe Sechzehntel-Position: gleiche Tonhöhe wird zusammengelegt, verschiedene werden ein Akkord (bekannte v1-Schwäche) |
| Starkes Rubato | Partitur entsteht trotzdem; Qualität kann schlecht sein (kein Abbruch) |
| Zielordner existiert nicht | wird angelegt |
| Zieldateien existieren | werden überschrieben |
| `testset score`: Stück nicht transkribiert oder ohne Audio | übersprungen mit Hinweis; kein Fehler |
| `testset score`: ein Stück scheitert | Meldung, übrige Stücke laufen weiter, Exit-Code ≠ 0 |

## Technical Constraints
- Performance: Nur CPU. `beat_this` läuft einmal pro Audiodatei und wird gecacht; Laufzeit im Plan messen. Alles nach Noten- und Beat-Cache (Quantisierung bis Export) in wenigen Sekunden pro Stück.
- Architektur: Teil B hängt nur an `NoteList` + Beat-Ergebnis, nicht am Transkriptions-Backend. Beat-Erkennung hinter einer eigenen Schnittstelle (später austauschbar, z. B. Schätzung aus Onsets für MIDI-Eingang). Ein internes Partitur-Modell (music21), Exporter getrennt.
- Security: keine besonderen Anforderungen; Modellgewichte nur aus der offiziellen Quelle.
- Compliance: Lizenz von `beat_this` und der Gewichte zur Kenntnis nehmen (Hobbyprojekt).

## Dependencies
- M0+M1 `transcribe-audio-to-midi`: NoteList, Cache, Aufräumen, MIDI-Export, CLI-Muster
- M2 `testset`: Manifest, gecachte Transkriptionen, Referenz-MusicXML (ASAP) für den Vergleich von Taktart und Taktzahl
- Neue Pakete: `beat_this`, `music21`
- Extern: MuseScore 4 nur für die manuelle Abnahme

## Open Questions
- [ ] Installation von `beat_this` unter Windows/CPU (Paketquelle, Gewichte-Download, Laufzeit) — im Plan früh klären; `madmom` nur als Notlösung.
- [ ] Liefert `beat_this` bei 6/8 punktierte Viertel oder Achtel als Beats? Bestimmt, wie `--time-sig 6/8` die Beats deutet.
- [ ] Konkrete Parameter der Handtrennung (Hysterese, Spannweitenlimit) — im Plan festlegen, am Testset prüfen.
- [ ] Format der Beat-Datei: JSON reicht, oder zusätzlich eine Marker-Datei für Audacity/Sonic Visualiser?
