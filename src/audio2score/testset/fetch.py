"""Testset-Download: MAESTRO-Audio per HTTP-Range aus dem Zip, ASAP-Dateien von GitHub."""

import io
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import soundfile as sf

from audio2score.testset.manifest import Entry, FetchSpec, Manifest

MAESTRO_ZIP_URL = (
    "https://storage.googleapis.com/magentadata/datasets/maestro/v3.0.0/maestro-v3.0.0.zip"
)
MAESTRO_PREFIX = "maestro-v3.0.0/"
ASAP_COMMIT = "afc815c75c42e83a79c03feb6da8a35e77d4c6b8"
ASAP_BASE_URL = f"https://raw.githubusercontent.com/fosfrancesco/asap-dataset/{ASAP_COMMIT}"

TIMEOUT = 30
RETRIES = 3
RETRY_DELAY = 1.0
MAX_RANGE = 8 << 20  # größte Anfrage pro Range-Request
BUFFER = 1 << 20  # Lesepuffer über dem Zip, damit zipfile nicht Byte für Byte anfragt
_FORMATS = {".flac": "FLAC", ".wav": "WAV"}

Progress = Callable[[str, int, int], None]  # (Eintrag-ID, geladene Bytes, Gesamtbytes)


class FetchError(Exception):
    pass


def _get(url: str, headers: dict[str, str] | None = None, method: str = "GET"):
    """(Status, Header, Body); wiederholt bei Netz- und 5xx-Fehlern, 4xx bricht sofort ab."""
    last: Exception | None = None
    for attempt in range(RETRIES):
        if attempt:
            time.sleep(RETRY_DELAY)
        request = urllib.request.Request(url, headers=headers or {}, method=method)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as resp:
                return resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code < 500:
                break
        except (urllib.error.URLError, OSError) as e:
            last = e
    raise FetchError(f"{url}: {last}")


class RangeFile(io.RawIOBase):
    """Seekbares, lesendes Datei-Objekt über HTTP-Range-Requests."""

    def __init__(self, url: str):
        super().__init__()
        self.url = url
        _, headers, _ = _get(url, method="HEAD")
        try:
            self.size = int(headers["Content-Length"])
        except (KeyError, TypeError, ValueError):
            raise FetchError(f"{url}: Server liefert keine Content-Length") from None
        self._pos = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self._pos, io.SEEK_END: self.size}[whence]
        self._pos = max(base + offset, 0)
        return self._pos

    def readinto(self, buffer) -> int:
        n = min(len(buffer), self.size - self._pos, MAX_RANGE)
        if n <= 0:
            return 0
        range_header = f"bytes={self._pos}-{self._pos + n - 1}"
        status, _, body = _get(self.url, {"Range": range_header})
        if status != 206:
            raise FetchError(f"{self.url}: Server unterstützt keine Range-Requests")
        body = body[:n]
        buffer[: len(body)] = body
        self._pos += len(body)
        return len(body)


def _write_atomic(dest: Path, data: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    try:
        part.write_bytes(data)
        os.replace(part, dest)
    finally:
        part.unlink(missing_ok=True)


@dataclass
class FetchResult:
    id: str
    status: Literal["ok", "present", "skipped", "failed"]
    message: str = ""


class Fetcher:
    """Lädt Einträge; das MAESTRO-Zip-Verzeichnis wird einmal pro Fetcher geöffnet."""

    def __init__(self, force: bool = False, on_progress: Progress | None = None):
        self.force = force
        self.on_progress = on_progress
        self._zip: zipfile.ZipFile | None = None

    def close(self) -> None:
        if self._zip is not None:
            self._zip.close()
            self._zip = None

    def _maestro_zip(self) -> zipfile.ZipFile:
        if self._zip is None:
            raw = io.BufferedReader(RangeFile(MAESTRO_ZIP_URL), BUFFER)
            try:
                self._zip = zipfile.ZipFile(raw)
            except zipfile.BadZipFile as e:
                raise FetchError(f"{MAESTRO_ZIP_URL}: kein gültiges Zip ({e})") from e
        return self._zip

    def _wanted(self, dest: Path | None) -> bool:
        return dest is not None and (self.force or not dest.is_file())

    def fetch(self, entry: Entry) -> bool:
        """True, wenn etwas geladen wurde. Wirft FetchError (mit Eintrag-ID)."""
        spec = entry.fetch
        if spec is None:
            return False
        try:
            did = False
            if spec.maestro_audio:
                did |= self._fetch_maestro(entry, spec)
            if spec.asap_folder:
                did |= self._fetch_asap(entry, spec)
            return did
        except (FetchError, zipfile.BadZipFile, OSError, sf.LibsndfileError) as e:
            raise FetchError(f"{entry.id}: {e}") from e

    def _fetch_maestro(self, entry: Entry, spec: FetchSpec) -> bool:
        if entry.audio is None:
            raise FetchError("fetch.maestro_audio braucht einen 'audio'-Pfad")
        did = False
        if self._wanted(entry.audio):
            self._maestro_audio(entry, spec)
            did = True
        if entry.source == "maestro" and self._wanted(entry.ref_midi):
            member = spec.maestro_audio.rsplit(".", 1)[0] + ".midi"
            _write_atomic(entry.ref_midi, self._read_member(entry, member))
            did = True
        return did

    def _open_member(self, member: str) -> zipfile.ZipInfo:
        try:
            return self._maestro_zip().getinfo(MAESTRO_PREFIX + member)
        except KeyError:
            raise FetchError(f"{member} nicht im MAESTRO-Zip gefunden") from None

    def _read_member(self, entry: Entry, member: str) -> bytes:
        info = self._open_member(member)
        with self._maestro_zip().open(info) as src:
            return src.read()

    def _maestro_audio(self, entry: Entry, spec: FetchSpec) -> None:
        dest = entry.audio
        dest.parent.mkdir(parents=True, exist_ok=True)
        info = self._open_member(spec.maestro_audio)
        source = dest.with_name(dest.name + ".dl.part")
        final = dest.with_name(dest.name + ".part")
        crop = spec.start is not None or spec.end is not None
        same_format = dest.suffix.lower() == Path(spec.maestro_audio).suffix.lower()
        try:
            with self._maestro_zip().open(info) as src, open(source, "wb") as out:
                done = 0
                while block := src.read(1 << 20):
                    out.write(block)
                    done += len(block)
                    if self.on_progress:
                        self.on_progress(entry.id, done, info.file_size)
            if not crop and same_format:
                os.replace(source, dest)
                return
            fmt = _FORMATS.get(dest.suffix.lower())
            if fmt is None:
                raise FetchError(f"Zielformat '{dest.suffix}' wird nicht unterstützt (flac, wav)")
            with sf.SoundFile(source) as f:
                rate = f.samplerate
                start = round((spec.start or 0.0) * rate)
                stop = None if spec.end is None else round(spec.end * rate)
                f.seek(min(start, f.frames))
                data = f.read(-1 if stop is None else max(stop - start, 0), dtype="int16")
            if len(data) == 0:
                raise FetchError(f"Ausschnitt {spec.start}-{spec.end} s ist leer")
            sf.write(final, data, rate, format=fmt, subtype="PCM_16")
            os.replace(final, dest)
        finally:
            source.unlink(missing_ok=True)
            final.unlink(missing_ok=True)

    def _fetch_asap(self, entry: Entry, spec: FetchSpec) -> bool:
        folder, perf = spec.asap_folder, spec.asap_performance
        files = (
            (entry.ref_musicxml, "xml_score.musicxml"),
            (entry.ref_midi, f"{perf}.mid"),
            (entry.ref_annotations, f"{perf}_annotations.txt"),
        )
        did = False
        for dest, name in files:
            if not self._wanted(dest):
                continue
            url = f"{ASAP_BASE_URL}/{urllib.parse.quote(f'{folder}/{name}', safe='/')}"
            _, _, body = _get(url)
            _write_atomic(dest, body)
            did = True
        return did


def fetch_entry(entry: Entry, force: bool = False, on_progress: Progress | None = None) -> None:
    fetcher = Fetcher(force, on_progress)
    try:
        fetcher.fetch(entry)
    finally:
        fetcher.close()


def fetch_all(
    manifest: Manifest,
    only: list[str] | None = None,
    force: bool = False,
    on_progress: Progress | None = None,
    on_result: Callable[[FetchResult], None] | None = None,
) -> list[FetchResult]:
    """Lädt alle (oder die gewählten) Einträge; ein Fehler stoppt die übrigen nicht."""
    fetcher = Fetcher(force, on_progress)
    results = []
    try:
        for entry in manifest.entries:
            if only and entry.id not in only:
                continue
            if entry.fetch is None:
                result = FetchResult(entry.id, "skipped", "kein fetch-Block")
            else:
                try:
                    did = fetcher.fetch(entry)
                    result = FetchResult(entry.id, "ok" if did else "present")
                except FetchError as e:
                    result = FetchResult(entry.id, "failed", str(e))
            results.append(result)
            if on_result:
                on_result(result)
    finally:
        fetcher.close()
    return results
