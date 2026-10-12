import hashlib
import json
import logging
import os
import re
from pathlib import Path

from audio2score.model import NoteList
from audio2score.rhythm.base import Beats, BeatTracker
from audio2score.transcribe.base import Transcriber

SCHEMA = 1
ENV_VAR = "AUDIO2SCORE_CACHE"
log = logging.getLogger(__name__)


def resolve_cache_dir(option: Path | None) -> Path:
    """Option > Umgebungsvariable AUDIO2SCORE_CACHE > ./cache."""
    if option is not None:
        return Path(option)
    env = os.environ.get(ENV_VAR)
    return Path(env) if env else Path("cache")


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _key(audio_path: Path, infix: str, name: str, version: str) -> str:
    suffix = re.sub(r"[^A-Za-z0-9_.+=-]", "_", f"{name}-{version}")
    return f"{_file_sha256(Path(audio_path))}-{infix}{suffix}"


def cache_key(audio_path: Path, transcriber: Transcriber) -> str:
    """sha256(Dateiinhalt) + Backend-Name + Backend-Version, dateinamentauglich."""
    return _key(audio_path, "", transcriber.name, transcriber.version)


def beat_cache_key(audio_path: Path, tracker: BeatTracker) -> str:
    """Wie `cache_key`, mit `-beats-` davor: getrennt vom Noten-Cache."""
    return _key(audio_path, "beats-", tracker.name, tracker.version)


def load(cache_dir: Path, key: str) -> NoteList | None:
    """None bei fehlendem, beschädigtem oder veraltetem Eintrag (mit Warnung)."""
    path = Path(cache_dir) / f"{key}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") != SCHEMA:
            log.warning("Cache-Eintrag %s hat ein anderes Schema und wird neu berechnet", key)
            return None
        return NoteList.from_dict(data["notelist"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        log.warning("Cache-Eintrag %s ist beschädigt (%s) und wird neu berechnet", key, e)
        return None


def save(cache_dir: Path, key: str, notelist: NoteList) -> None:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{key}.json"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"schema": SCHEMA, "notelist": notelist.to_dict()}), encoding="utf-8")
    os.replace(tmp, path)


def load_beats(cache_dir: Path, key: str) -> Beats | None:
    """None bei fehlendem, beschädigtem oder veraltetem Eintrag (mit Warnung)."""
    path = Path(cache_dir) / f"{key}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") != SCHEMA:
            log.warning("Beat-Cache-Eintrag %s hat ein anderes Schema und wird neu berechnet", key)
            return None
        return Beats.from_dict(data["beats"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        log.warning("Beat-Cache-Eintrag %s ist beschädigt (%s) und wird neu berechnet", key, e)
        return None


def save_beats(cache_dir: Path, key: str, beats: Beats) -> None:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{key}.json"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"schema": SCHEMA, "beats": beats.to_dict()}), encoding="utf-8")
    os.replace(tmp, path)
