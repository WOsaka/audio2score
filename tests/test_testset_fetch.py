import io
import re
import threading
import zipfile
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pretty_midi
import pytest
import soundfile as sf

from audio2score.testset import fetch as fetch_mod
from audio2score.testset.fetch import FetchError, RangeFile, fetch_all, fetch_entry
from audio2score.testset.manifest import Entry, FetchSpec, Manifest

SR = 44_100


class Server:
    def __init__(self):
        self.routes: dict[str, bytes] = {}
        self.fail: set[str] = set()
        self.requests: list[tuple[str, str]] = []
        self.ranges = True
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _serve(self, head):
                outer.requests.append((self.command, self.path))
                if self.path in outer.fail:
                    return self.send_error(500)
                data = outer.routes.get(self.path)
                if data is None:
                    return self.send_error(404)
                rng = self.headers.get("Range")
                match = re.fullmatch(r"bytes=(\d+)-(\d*)", rng or "")
                if match and outer.ranges and not head:
                    a = int(match[1])
                    b = min(int(match[2] or len(data) - 1), len(data) - 1)
                    self.send_response(206)
                    self.send_header("Content-Range", f"bytes {a}-{b}/{len(data)}")
                    body = data[a : b + 1]
                else:
                    self.send_response(200)
                    body = data
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if not head:
                    self.wfile.write(body)

            def do_GET(self):
                self._serve(False)

            def do_HEAD(self):
                self._serve(True)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def gets(self):
        return [p for m, p in self.requests if m == "GET"]


@pytest.fixture
def server(monkeypatch):
    s = Server()
    monkeypatch.setattr(fetch_mod, "RETRY_DELAY", 0.0)
    monkeypatch.setattr(fetch_mod, "MAESTRO_ZIP_URL", f"{s.url}/maestro.zip")
    monkeypatch.setattr(fetch_mod, "ASAP_BASE_URL", f"{s.url}/asap")
    yield s
    s.httpd.shutdown()


def wav_bytes(seconds=3.0):
    t = np.arange(int(SR * seconds)) / SR
    y = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, np.stack([y, y], axis=1), SR, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def midi_bytes():
    midi = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(program=0)
    inst.notes.append(pretty_midi.Note(80, 60, 0.0, 1.0))
    midi.instruments.append(inst)
    buf = io.BytesIO()
    midi.write(buf)
    return buf.getvalue()


def maestro_zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for name, data in members.items():
            z.writestr(f"maestro-v3.0.0/{name}", data)
    return buf.getvalue()


def entry(tmp_path, source="maestro", audio="maestro/x.wav", fetch=None, eid="piece", **paths):
    resolved = {k: tmp_path / v for k, v in paths.items()}
    return Entry(
        id=eid, style="classical", source=source, quality="studio", license="l", origin="o",
        audio=tmp_path / audio if audio else None, fetch=fetch, **resolved,
    )  # fmt: skip


def test_range_file_reads_arbitrary_ranges(server):
    data = bytes(range(256)) * 100
    server.routes["/blob"] = data
    with RangeFile(f"{server.url}/blob") as f:
        assert f.seek(0, io.SEEK_END) == len(data)
        f.seek(1000)
        assert f.read(50) == data[1000:1050]
        f.seek(-10, io.SEEK_END)
        assert f.read() == data[-10:]
        f.seek(0)
        assert f.read(len(data)) == data


def test_range_file_requires_range_support(server):
    server.routes["/blob"] = b"x" * 100
    server.ranges = False
    with pytest.raises(FetchError, match="Range"):
        RangeFile(f"{server.url}/blob").read(10)


def test_range_file_retries_then_fails(server):
    server.fail.add("/blob")
    with pytest.raises(FetchError) as exc:
        RangeFile(f"{server.url}/blob")
    assert "/blob" in str(exc.value)
    assert len([r for r in server.requests if r[1] == "/blob"]) == fetch_mod.RETRIES


def test_maestro_audio_is_copied_unchanged(server, tmp_path):
    wav = wav_bytes()
    server.routes["/maestro.zip"] = maestro_zip({"2008/a.wav": wav, "2008/b.wav": b"other"})
    e = entry(tmp_path, fetch=FetchSpec(maestro_audio="2008/a.wav"))
    fetch_entry(e)
    assert e.audio.read_bytes() == wav
    assert not list(tmp_path.rglob("*.part"))


def test_maestro_midi_is_fetched_for_maestro_source(server, tmp_path):
    midi = midi_bytes()
    server.routes["/maestro.zip"] = maestro_zip({"2008/a.wav": wav_bytes(), "2008/a.midi": midi})
    e = entry(tmp_path, ref_midi="maestro/x.midi", fetch=FetchSpec(maestro_audio="2008/a.wav"))
    fetch_entry(e)
    assert e.ref_midi.read_bytes() == midi


def test_crop_to_flac(server, tmp_path):
    server.routes["/maestro.zip"] = maestro_zip({"2008/a.wav": wav_bytes(3.0)})
    e = entry(
        tmp_path, source="asap", audio="asap/x.flac",
        fetch=FetchSpec(maestro_audio="2008/a.wav", start=1.0, end=2.5),
    )  # fmt: skip
    fetch_entry(e)
    info = sf.info(e.audio)
    assert info.format == "FLAC"
    assert info.frames == int(1.5 * SR)
    assert not list(tmp_path.rglob("*.part"))


def test_crop_is_deterministic(server, tmp_path):
    server.routes["/maestro.zip"] = maestro_zip({"2008/a.wav": wav_bytes(3.0)})
    spec = FetchSpec(maestro_audio="2008/a.wav", start=0.5, end=2.0)
    one = entry(tmp_path / "1", audio="x.flac", fetch=spec)
    two = entry(tmp_path / "2", audio="x.flac", fetch=spec)
    fetch_entry(one)
    fetch_entry(two)
    assert one.audio.read_bytes() == two.audio.read_bytes()


def test_existing_files_are_skipped_and_force_reloads(server, tmp_path):
    server.routes["/maestro.zip"] = maestro_zip({"2008/a.wav": wav_bytes()})
    e = entry(tmp_path, fetch=FetchSpec(maestro_audio="2008/a.wav"))
    fetch_entry(e)
    n = len(server.requests)
    fetch_entry(e)
    assert len(server.requests) == n
    e.audio.write_bytes(b"corrupt")
    fetch_entry(e, force=True)
    assert e.audio.read_bytes() != b"corrupt"


def test_asap_files_land_at_manifest_paths(server, tmp_path):
    base = "/asap/Bach/Prelude/bwv_846"
    server.routes[f"{base}/xml_score.musicxml"] = b"<score-partwise/>"
    server.routes[f"{base}/Shi05M.mid"] = midi_bytes()
    server.routes[f"{base}/Shi05M_annotations.txt"] = b"0.5\t0.5\tdb\n"
    e = entry(
        tmp_path, source="asap", audio=None, ref_midi="asap/p.mid",
        ref_musicxml="asap/p.musicxml", ref_annotations="asap/p.txt",
        fetch=FetchSpec(asap_folder="Bach/Prelude/bwv_846", asap_performance="Shi05M"),
    )  # fmt: skip
    fetch_entry(e)
    assert e.ref_musicxml.read_bytes() == b"<score-partwise/>"
    assert e.ref_annotations.read_bytes() == b"0.5\t0.5\tdb\n"
    assert pretty_midi.PrettyMIDI(str(e.ref_midi)).instruments


def test_asap_only_fetches_declared_files(server, tmp_path):
    base = "/asap/Bach/Prelude/bwv_846"
    server.routes[f"{base}/Shi05M.mid"] = midi_bytes()
    e = entry(
        tmp_path, source="asap", audio=None, ref_midi="asap/p.mid",
        fetch=FetchSpec(asap_folder="Bach/Prelude/bwv_846", asap_performance="Shi05M"),
    )  # fmt: skip
    fetch_entry(e)
    assert server.gets() == [f"{base}/Shi05M.mid"]


def test_http_error_raises_fetch_error_with_id_and_url_and_leaves_no_part(server, tmp_path):
    e = entry(
        tmp_path, source="asap", audio=None, ref_midi="asap/p.mid",
        fetch=FetchSpec(asap_folder="Missing/Folder", asap_performance="X"),
    )  # fmt: skip
    with pytest.raises(FetchError) as exc:
        fetch_entry(e)
    assert "piece" in str(exc.value) and "Missing/Folder" in str(exc.value)
    assert not list(tmp_path.rglob("*.part"))
    assert not e.ref_midi.exists()


def test_maestro_member_missing_in_zip(server, tmp_path):
    server.routes["/maestro.zip"] = maestro_zip({"2008/a.wav": wav_bytes()})
    e = entry(tmp_path, fetch=FetchSpec(maestro_audio="2008/nope.wav"))
    with pytest.raises(FetchError, match="nope.wav"):
        fetch_entry(e)


def test_connection_dropped_mid_download_leaves_no_part(server, tmp_path, monkeypatch):
    server.routes["/maestro.zip"] = maestro_zip({"2008/a.wav": wav_bytes(30.0)})
    real = fetch_mod.RangeFile.readinto
    state = {"n": 0}

    def flaky(self, b):
        state["n"] += 1
        if state["n"] > 4:
            raise FetchError("piece: Verbindung abgebrochen")
        return real(self, b)

    monkeypatch.setattr(fetch_mod.RangeFile, "readinto", flaky)
    e = entry(tmp_path, fetch=FetchSpec(maestro_audio="2008/a.wav"))
    with pytest.raises(FetchError):
        fetch_entry(e)
    assert not list(tmp_path.rglob("*.part"))
    assert not e.audio.exists()


def test_fetch_all_continues_after_failure_and_opens_zip_once(server, tmp_path):
    server.routes["/maestro.zip"] = maestro_zip(
        {"2008/a.wav": wav_bytes(), "2008/b.wav": wav_bytes()}
    )
    entries = [
        entry(tmp_path, audio="maestro/a.wav", eid="good1",
              fetch=FetchSpec(maestro_audio="2008/a.wav")),
        entry(tmp_path, audio="maestro/bad.wav", eid="bad",
              fetch=FetchSpec(maestro_audio="2008/no.wav")),
        entry(tmp_path, audio="maestro/b.wav", eid="good2",
              fetch=FetchSpec(maestro_audio="2008/b.wav")),
        entry(tmp_path, source="own", audio="own/c.wav", eid="own"),
    ]  # fmt: skip
    manifest = Manifest(path=tmp_path / "m.yaml", data_dir=tmp_path, entries=entries)
    results = fetch_all(manifest)
    assert [(r.id, r.status) for r in results] == [
        ("good1", "ok"), ("bad", "failed"), ("good2", "ok"), ("own", "skipped"),
    ]  # fmt: skip
    assert "no.wav" in results[1].message
    assert entries[0].audio.exists() and entries[2].audio.exists()
    assert server.requests.count(("HEAD", "/maestro.zip")) == 1


def test_fetch_all_only_filter(server, tmp_path):
    server.routes["/maestro.zip"] = maestro_zip({"2008/a.wav": wav_bytes()})
    e = replace(entry(tmp_path, fetch=FetchSpec(maestro_audio="2008/a.wav")), id="x")
    manifest = Manifest(path=tmp_path / "m.yaml", data_dir=tmp_path, entries=[e])
    assert fetch_all(manifest, only=["other"]) == []
    assert [r.status for r in fetch_all(manifest, only=["x"])] == ["ok"]


def test_convert_to_flac_without_start_and_end(server, tmp_path):
    server.routes["/maestro.zip"] = maestro_zip({"2008/a.wav": wav_bytes(2.0)})
    e = entry(
        tmp_path, source="asap", audio="asap/x.flac", fetch=FetchSpec(maestro_audio="2008/a.wav")
    )
    fetch_entry(e)
    info = sf.info(e.audio)
    assert info.format == "FLAC" and info.frames == 2 * SR
