# audio2score

Klavieraufnahme rein, Noten raus: automatische Transkription von Klavier-Audio zu MIDI, MusicXML, PDF und Lead Sheet.

```
Audio → Transkriptionsmodell → Noten-Events (MIDI)        ← Teil A
      → Beats/Takt → Quantisierung → Tonart/Spelling
      → Hände/Stimmen → Partitur (MusicXML, PDF, Lead Sheet) ← Teil B
```

Status: Planungsphase — siehe [`docs/roadmap.md`](docs/roadmap.md).

## Voraussetzungen

- Python 3.12
- ffmpeg im `PATH`
- MuseScore 4 (für PDF-Export)

Entwicklungsablauf und Konventionen: siehe `CLAUDE.md`.
