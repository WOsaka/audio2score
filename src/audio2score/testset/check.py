"""Dateiprüfung pro Testset-Eintrag: vorhanden und lesbar."""

import struct
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pretty_midi
import soundfile as sf

from audio2score.audio.load import find_ffmpeg
from audio2score.testset.manifest import Entry

_SCORE_ROOTS = ("score-partwise", "score-timewise")


@dataclass(frozen=True)
class Issue:
    level: Literal["warn", "error"]
    message: str


def _error(path: Path, reason: str) -> list[Issue]:
    return [Issue("error", f"{path}: {reason}")]


def _wav_truncated(path: Path) -> bool:
    """Deklarierte Länge des data-Chunks größer als die Datei (libsndfile merkt das nicht)."""
    size = path.stat().st_size
    with open(path, "rb") as f:
        header = f.read(12)
        if header[:4] not in (b"RIFF", b"RF64") or header[8:12] != b"WAVE":
            return False
        pos = 12
        while pos + 8 <= size:
            f.seek(pos)
            chunk_id, length = struct.unpack("<4sI", f.read(8))
            if chunk_id == b"data":
                return length != 0xFFFFFFFF and pos + 8 + length > size
            pos += 8 + length + (length & 1)
    return False


def _check_audio(path: Path) -> list[Issue]:
    try:
        if path.suffix.lower() == ".wav" and _wav_truncated(path):
            return _error(path, "WAV ist abgeschnitten")
        info = sf.info(path)
        if info.frames == 0:
            return _error(path, "Audio ist leer")
        # Abgeschnittene Dateien: das Ende muss wirklich lesbar sein
        with sf.SoundFile(path) as f:
            f.seek(max(info.frames - 1, 0))
            if len(f.read(1)) == 0:
                return _error(path, "Audio ist abgeschnitten")
        return []
    except (sf.LibsndfileError, RuntimeError):
        pass
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        return _error(path, "Audio nicht lesbar, und ffmpeg wurde nicht gefunden")
    proc = subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(path), "-f", "null", "-"], capture_output=True
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode(errors="replace").strip().splitlines()
        return _error(path, f"Audio nicht lesbar: {detail[-1] if detail else 'unbekannter Fehler'}")
    return []


def _check_midi(path: Path) -> list[Issue]:
    try:
        midi = pretty_midi.PrettyMIDI(str(path))
    except Exception as e:  # pretty_midi/mido werfen uneinheitliche Typen
        return _error(path, f"MIDI nicht lesbar: {e}")
    if not any(inst.notes for inst in midi.instruments if not inst.is_drum):
        return [Issue("warn", f"{path}: MIDI enthält keine Noten")]
    return []


def _score_root(path: Path) -> str:
    """Wurzelelement der MusicXML-Datei; .mxl wird als Zip geöffnet."""
    if path.suffix.lower() == ".mxl":
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.lower().endswith((".xml", ".musicxml"))]
            for name in names:
                if name.startswith("META-INF/"):
                    continue
                with z.open(name) as f:
                    return _first_tag(f)
        raise ValueError("keine MusicXML-Datei im Archiv")
    with open(path, "rb") as f:
        return _first_tag(f)


def _first_tag(stream) -> str:
    """Wurzel-Tag; parst das ganze Dokument, damit Wohlgeformtheit geprüft ist."""
    tag = ""
    for event, elem in ET.iterparse(stream, events=("start", "end")):
        if not tag and event == "start":
            tag = elem.tag
    return tag.rsplit("}", 1)[-1]


def _check_musicxml(path: Path) -> list[Issue]:
    try:
        root = _score_root(path)
    except (ET.ParseError, zipfile.BadZipFile, ValueError, OSError) as e:
        return _error(path, f"MusicXML nicht lesbar: {e}")
    if root not in _SCORE_ROOTS:
        return _error(path, f"MusicXML hat Wurzel '{root}', erwartet {' oder '.join(_SCORE_ROOTS)}")
    return []


def _check_annotations(path: Path) -> list[Issue]:
    try:
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except (OSError, UnicodeDecodeError) as e:
        return _error(path, f"Annotationen nicht lesbar: {e}")
    if not lines:
        return _error(path, "Annotationen sind leer")
    for number, line in enumerate(lines, 1):
        fields = line.split("\t")
        try:
            if len(fields) < 3:
                raise ValueError
            float(fields[0]), float(fields[1])
        except ValueError:
            return _error(path, f"Annotationen, Zeile {number}: erwartet 'Zeit<TAB>Zeit<TAB>Label'")
    return []


_CHECKS = (
    ("audio", _check_audio),
    ("ref_midi", _check_midi),
    ("ref_musicxml", _check_musicxml),
    ("ref_annotations", _check_annotations),
)


def check_entry(entry: Entry) -> list[Issue]:
    issues: list[Issue] = []
    for field, check in _CHECKS:
        path = getattr(entry, field)
        if path is None:
            continue
        if not path.is_file():
            issues += _error(path, f"{field}: Datei fehlt")
        else:
            issues += check(path)
    return issues
