# Testset

Feste Sammlung von Stücken mit Referenzen, gegen die jede Änderung an Teil A (Audio → Noten) und
später Teil B (Noten → Partitur) gemessen wird. Eingecheckt ist nur `manifest.yaml`; die Daten
liegen unter `data/testset/` (nicht im Repo, siehe `.gitignore`).

## Befehle

```
audio2score testset fetch      # ASAP- und MAESTRO-Stücke laden (fortsetzbar; --force, --only ID)
audio2score testset check      # Vollständigkeit und Lesbarkeit prüfen (Exit-Code 1 bei Fehlern)
audio2score testset transcribe # Teil A für alle Audio-Stücke in den Cache (fortsetzbar)
audio2score testset baseline   # Note-F1 pro Stück, Mittel pro Stil und Qualität, nur aus dem Cache
```

Gemeinsame Optionen: `--manifest` (sonst `AUDIO2SCORE_TESTSET`, sonst `testset/manifest.yaml`) und
`--data-dir`. `transcribe` und `baseline` nehmen zusätzlich `--backend` und `--cache-dir`.

Ablauf im frischen Checkout: `fetch` → `check` → `transcribe` (≈ Echtzeit auf der CPU, ~50 min für
das ganze Set, danach Cache) → `baseline`.

## Eigene Aufnahmen und Internet-Mitschnitte

1. Datei nach `data/testset/own/` (bzw. `internet/`) legen.
2. Eintrag in `manifest.yaml` anlegen: `audio`, `license`, `origin`, ggf. `ref_midi` / `ref_musicxml`.
   (Es gibt noch keine Improvisation, Stil `free`.)
3. `audio2score testset check`.

Einträge ohne `fetch`-Block werden nie geladen. Mitschnitte aus dem Internet bleiben lokal.

## Felder eines Eintrags

| Feld | Pflicht | Bedeutung |
|---|---|---|
| `id` | ja | eindeutig, kebab-case |
| `style` | ja | `classical` · `pop` · `jazz` · `free` |
| `source` | ja | `asap` · `maestro` · `own` · `internet` |
| `quality` | ja | `studio` · `phone` · `internet` |
| `license`, `origin` | ja | Lizenz und Herkunft |
| `audio` | * | Audiodatei, relativ zu `data_dir` |
| `ref_midi` | * | Referenz-MIDI, zeitlich passend zum Audio (Grundlage der F1) |
| `ref_musicxml` | nein | Referenz-Partitur |
| `ref_annotations` | nein | ASAP-Annotationen (Beats, Downbeats, Taktart, Tonart) für M3 |
| `time_sig`, `tempo_hint`, `notes` | nein | Hinweise |
| `fetch` | nein | Quelle für `testset fetch` (siehe unten) |

\* mindestens eines von `audio` / `ref_midi`. Ein Eintrag nur mit `ref_midi` (kein Audio) gilt als
direkte Teil-B-Eingabe; `transcribe` überspringt ihn.

### `fetch`

- `maestro_audio`: Pfad der WAV im MAESTRO-v3-Zip (ohne `maestro-v3.0.0/`). Das Zip (108 GB) wird
  nie ganz geladen, nur die benötigte Datei per HTTP-Range. Bei Einträgen mit `source: maestro`
  wird die gleichnamige `.midi` als `ref_midi` mitgeladen.
- `start`, `end` (Sekunden): Ausschnitt; das Ergebnis wird als FLAC/WAV nach der Endung von `audio`
  geschrieben (16 Bit). Ohne beide Werte wird das Audio unverändert kopiert.
- `asap_folder`, `asap_performance`: ASAP-Dateien (`xml_score.musicxml`, `<perf>.mid`,
  `<perf>_annotations.txt`) vom festen Commit `afc815c…` des ASAP-Repos.

**Zeitbezug ASAP ↔ MAESTRO-Audio:** Die ASAP-Performance-MIDI stimmt mit der MAESTRO-MIDI überein,
verschoben um `start`, wobei ASAP bei `start > 0` 0,5 s Vorlauf lässt: die MIDI beginnt bei
`start − 0,5 s`. Deshalb steht bei `asap-bach-fugue-bwv856` `start: 59.478125` statt der 59,978125
aus `metadata.csv`. Bei den übrigen Stücken ist `start = 0`, der Versatz null (alle 548–3203 Noten
je Stück auf die Millisekunde geprüft).

## Hinweise

- Der Cache-Schlüssel ist der Datei-Hash. Zuschnitt und FLAC-Kodierung sind deterministisch; bei
  einer anderen libsndfile-Version können neu geladene Dateien neu transkribiert werden.
- `MAESTRO` und `ASAP`: CC BY-NC-SA 4.0 (nicht kommerzielle Nutzung).
