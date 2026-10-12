"""Testset-Manifest: YAML laden, Pfade auflösen, alle Fehler sammeln."""

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Literal

import yaml

DEFAULT_MANIFEST = Path("testset") / "manifest.yaml"
ENV_VAR = "AUDIO2SCORE_TESTSET"

Style = Literal["classical", "pop", "jazz", "free"]
Source = Literal["asap", "maestro", "own", "internet"]
Quality = Literal["studio", "phone", "internet"]

STYLES = ("classical", "pop", "jazz", "free")
SOURCES = ("asap", "maestro", "own", "internet")
QUALITIES = ("studio", "phone", "internet")

_PATH_FIELDS = ("audio", "ref_midi", "ref_musicxml", "ref_annotations")
_ENTRY_FIELDS = {
    "id", "style", "source", "quality", "license", "origin", "time_sig", "tempo_hint", "notes",
    "fetch", *_PATH_FIELDS,
}  # fmt: skip
_FETCH_FIELDS = {"maestro_audio", "asap_folder", "asap_performance", "start", "end"}
_KEBAB = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


class ManifestError(Exception):
    """Ungültiges Manifest; `errors` enthält jeden Fehler mit Eintrag-ID und Grund."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


@dataclass(frozen=True)
class FetchSpec:
    maestro_audio: str | None = None  # Pfad im MAESTRO-Zip (ohne Präfix maestro-v3.0.0/)
    asap_folder: str | None = None
    asap_performance: str | None = None
    start: float | None = None
    end: float | None = None


@dataclass(frozen=True)
class Entry:
    id: str
    style: Style
    source: Source
    quality: Quality
    license: str
    origin: str
    audio: Path | None = None
    ref_midi: Path | None = None
    ref_musicxml: Path | None = None
    ref_annotations: Path | None = None
    time_sig: str | None = None
    tempo_hint: float | None = None
    notes: str = ""
    fetch: FetchSpec | None = None


@dataclass
class Manifest:
    path: Path
    data_dir: Path
    entries: list[Entry]


def _resolve(data_dir: Path, value: str) -> Path | None:
    """None, wenn der Pfad absolut ist oder aus data_dir herausführt."""
    if PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute():
        return None
    if PureWindowsPath(value).drive:
        return None
    path = (data_dir / value).resolve()
    return path if path.is_relative_to(data_dir) else None


def _number(value) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _parse_fetch(raw, eid: str, errors: list[str]) -> FetchSpec | None:
    if not isinstance(raw, dict):
        errors.append(f"{eid}: fetch muss ein Block sein")
        return None
    before = len(errors)
    for key in sorted(set(raw) - _FETCH_FIELDS):
        errors.append(f"{eid}: unbekanntes Feld fetch.{key}")
    has_asap = raw.get("asap_folder") or raw.get("asap_performance")
    if not raw.get("maestro_audio") and not has_asap:
        errors.append(f"{eid}: fetch braucht maestro_audio oder asap_folder + asap_performance")
    if bool(raw.get("asap_folder")) != bool(raw.get("asap_performance")):
        errors.append(f"{eid}: fetch braucht asap_folder und asap_performance zusammen")
    for key in ("start", "end"):
        if raw.get(key) is not None and not _number(raw[key]):
            errors.append(f"{eid}: fetch.{key} muss eine Zahl sein")
    start, end = raw.get("start"), raw.get("end")
    if _number(start) and _number(end) and start >= end:
        errors.append(f"{eid}: fetch.start ({start}) muss kleiner als fetch.end ({end}) sein")
    if len(errors) > before:
        return None
    return FetchSpec(**{k: raw.get(k) for k in _FETCH_FIELDS})


def _parse_entry(raw, index: int, data_dir: Path, errors: list[str]) -> Entry | None:
    if not isinstance(raw, dict):
        errors.append(f"Eintrag {index + 1}: muss ein Mapping sein")
        return None
    eid = str(raw.get("id") or f"Eintrag {index + 1}")
    before = len(errors)

    for key in sorted(set(raw) - _ENTRY_FIELDS):
        errors.append(f"{eid}: unbekanntes Feld '{key}'")
    for key in ("id", "license", "origin"):
        if not raw.get(key):
            errors.append(f"{eid}: Pflichtfeld '{key}' fehlt")
    if raw.get("id") and not _KEBAB.fullmatch(str(raw["id"])):
        errors.append(f"{eid}: id muss kebab-case sein (a-z, 0-9, Bindestriche)")
    for key, allowed in (("style", STYLES), ("source", SOURCES), ("quality", QUALITIES)):
        value = raw.get(key)
        if value is None:
            errors.append(f"{eid}: Pflichtfeld '{key}' fehlt (erlaubt: {' | '.join(allowed)})")
        elif value not in allowed:
            errors.append(
                f"{eid}: ungültiger Wert '{value}' für {key} (erlaubt: {' | '.join(allowed)})"
            )
    if not raw.get("audio") and not raw.get("ref_midi"):
        errors.append(f"{eid}: mindestens eines von 'audio' / 'ref_midi' ist nötig")
    if raw.get("tempo_hint") is not None and not _number(raw["tempo_hint"]):
        errors.append(f"{eid}: tempo_hint muss eine Zahl sein")

    paths: dict[str, Path | None] = {}
    for key in _PATH_FIELDS:
        value = raw.get(key)
        if value is None:
            paths[key] = None
            continue
        paths[key] = _resolve(data_dir, str(value))
        if paths[key] is None:
            errors.append(f"{eid}: {key} '{value}' ist absolut oder führt aus data_dir heraus")

    fetch = _parse_fetch(raw["fetch"], eid, errors) if raw.get("fetch") is not None else None
    if "fetch" in raw and raw["fetch"] is None:
        errors.append(f"{eid}: fetch ist leer")

    if len(errors) > before:
        return None
    return Entry(
        id=raw["id"], style=raw["style"], source=raw["source"], quality=raw["quality"],
        license=raw["license"], origin=raw["origin"], time_sig=raw.get("time_sig"),
        tempo_hint=raw.get("tempo_hint"), notes=raw.get("notes") or "", fetch=fetch, **paths,
    )  # fmt: skip


def load_manifest(path: Path, data_dir: Path | None = None) -> Manifest:
    path = Path(path)
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise ManifestError([f"Manifest {path} nicht lesbar: {e.strerror or e}"]) from e
    except yaml.YAMLError as e:
        raise ManifestError([f"Manifest {path} ist kein gültiges YAML: {e}"]) from e
    if not isinstance(doc, dict):
        raise ManifestError([f"Manifest {path}: Wurzel muss ein Mapping sein"])

    errors: list[str] = []
    if doc.get("version") != 1:
        errors.append(f"Manifest: version muss 1 sein (ist {doc.get('version')!r})")
    raw_entries = doc.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        errors.append("Manifest: 'entries' fehlt oder ist leer")
        raw_entries = []

    if data_dir is None:
        data_dir = path.parent / doc.get("data_dir", "../data/testset")
    data_dir = Path(data_dir).resolve()

    entries: list[Entry] = []
    seen: set[str] = set()
    for i, raw in enumerate(raw_entries):
        eid = raw.get("id") if isinstance(raw, dict) else None
        if eid in seen:
            errors.append(f"{eid}: id ist doppelt")
        elif eid:
            seen.add(eid)
        entry = _parse_entry(raw, i, data_dir, errors)
        if entry:
            entries.append(entry)

    if errors:
        raise ManifestError(errors)
    return Manifest(path=path, data_dir=data_dir, entries=entries)
