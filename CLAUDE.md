# audio2score — Claude Code Instructions

## Projekt

Hobby-/Lernprojekt: Klavieraufnahmen (eigene Aufnahmen, Internet-Mitschnitte) werden automatisch in Noten umgewandelt — MIDI, MusicXML, PDF und Lead Sheet (Melodie + Akkorde). Stile: Klassik, Pop, Jazz, Improvisation. Zuerst CLI, später Web-Oberfläche.

Gesamtplan und Meilensteine: `docs/roadmap.md`.

## Tech-Stack & Befehle

- Sprache/Framework: Python 3.11, PyTorch (CPU-Build), music21, pretty_midi, librosa, Typer (CLI); extern: ffmpeg, MuseScore 4 (PDF)
- Hardware: **nur CPU** — Ergebnisse der Transkription (Teil A) immer cachen, Teil B muss ohne Modelllauf entwickelbar sein
- Tests: `pytest`
- Lint/Format: `ruff check . && ruff format .`
- Start lokal: `audio2score --help` (nach `pip install -e .[dev]`)

## Architektur-Leitlinien

- **Teil A** (Audio → Noten-Events) und **Teil B** (Noten-Events → Partitur) strikt getrennt; Teil B akzeptiert auch direkt MIDI.
- Transkriptions-Backends hinter einem gemeinsamen Protokoll (`transcribe/base.py`), austauschbar.
- Ein internes Partitur-Modell (music21), mehrere Exporter.
- Für die Notation Tasten-Offsets verwenden, nicht pedal-verlängerte.

## Projektstruktur

```
.claude/
  commands/         # Custom Slash Commands (Skills)
    feature/        # Feature-Workflow
    debug/          # Debugging-Workflow
  templates/        # MD-Vorlagen für die Skills
docs/
  roadmap.md              # Gesamtplan, Meilensteine → Features
  features/               # Feature-Specs (.md)
  implementation-plans/   # Implementierungspläne (.md)
  bugs/                   # Bug-Analysen und Fix-Pläne (.md)
src/audio2score/          # Paket (entsteht mit dem ersten Feature)
tests/
data/testset/             # Testaufnahmen + Referenzen (nicht eingecheckt)
cache/                    # Teil-A-Ergebnisse (nicht eingecheckt)
```

## Workflow

### Feature-Entwicklung
1. `/feature:spec` — Interview + Feature-Spec → `docs/features/<name>.md`
2. `/feature:implementation-plan` — Plan aus Spec → `docs/implementation-plans/<name>.md`
3. `/feature:code` — Umsetzung aus Plan (prüft Plan-Freigabe)

### Bugfixing
1. `/debug:analysis` — Bug analysieren → `docs/bugs/<name>-analysis.md`
2. `/debug:fix-plan` — Fix-Plan → `docs/bugs/<name>-fix-plan.md`
3. `/debug:fix` — Fix ausführen

## Konventionen

- Dateinamen in kebab-case: `docs/features/<name>.md`, `docs/implementation-plans/<name>.md`, `docs/bugs/<name>-analysis.md`, `<name>-fix-plan.md`
- Implementierungspläne brauchen `status: approved` im Frontmatter (manuell setzen), bevor `/feature:code` startet.
- Nach Abschluss eines Features den Status in `docs/roadmap.md` aktualisieren.

## Git-Arbeitsweise

- Claude arbeitet **immer auf `dev`**: vor Änderungen `git switch dev`, dort committen und pushen. Keine Feature-/Docs-Branches, außer der User verlangt es ausdrücklich.
- `main` ist der Release-Branch: nur per PR `dev → main` (der User merged). Nie direkt auf `main` committen oder pushen.
- Commit-Messages kurz, ohne `Co-Authored-By`-/Session-Footer.

## Superpowers Plugin

Das `superpowers`-Plugin ist in `.claude/settings.json` vorkonfiguriert (beim ersten Start Marketplace-Vertrauen bestätigen). Der Workflow oben hat Vorrang (kein `brainstorming` statt `/feature:spec`, kein `systematic-debugging` statt `/debug:analysis`). Ergänzend nutzen:
- `test-driven-development` bei der Umsetzung in `/feature:code`
- `verification-before-completion` vor `status: implemented` / `status: fixed`
- `requesting-code-review` / `receiving-code-review` vor dem Merge
- `using-git-worktrees` für isolierte Workspaces
