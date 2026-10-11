import os
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

import numpy as np

from audio2score.model import PITCH_MAX, PITCH_MIN, Note, NoteList, PedalEvent
from audio2score.transcribe.base import ModelDownloadError

CHECKPOINT_NAME = "note_F1=0.9677_pedal_F1=0.9186.pth"
CHECKPOINT_URL = (
    "https://zenodo.org/record/4034264/files/CRNN_note_F1%3D0.9677_pedal_F1%3D0.9186.pth?download=1"
)
MIN_CHECKPOINT_BYTES = int(1.6e8)  # gleiche Schwelle wie das Paket selbst
ENV_VAR = "AUDIO2SCORE_CHECKPOINT"
SAMPLE_RATE = 16_000

Progress = Callable[[int, int], None]  # (geladene Bytes, Gesamtbytes oder 0)


def default_checkpoint_path() -> Path:
    # Standardort des Pakets, damit vorhandene Downloads wiederverwendet werden
    return Path.home() / "piano_transcription_inference_data" / CHECKPOINT_NAME


def resolve_checkpoint(option: Path | None = None) -> Path:
    """--checkpoint > AUDIO2SCORE_CHECKPOINT > Standardort des Pakets."""
    if option is not None:
        return Path(option)
    env = os.environ.get(ENV_VAR)
    return Path(env) if env else default_checkpoint_path()


def download_checkpoint(dest: Path, url: str | None = None, progress: Progress | None = None):
    """Lädt nach `<dest>.part` und benennt erst nach vollständigem Download um."""
    url = url or CHECKPOINT_URL
    dest = Path(dest)
    part = dest.with_name(dest.name + ".part")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=30) as resp, open(part, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while block := resp.read(1 << 20):
                out.write(block)
                done += len(block)
                if progress:
                    progress(done, total)
        if total and done != total:
            raise OSError(f"unvollständig: {done} von {total} Bytes")
    except (urllib.error.URLError, OSError) as e:
        part.unlink(missing_ok=True)
        raise ModelDownloadError(
            f"Modellgewichte konnten nicht geladen werden ({e}).\n"
            f"URL: {url}\n"
            f"Die Datei manuell herunterladen und als {dest} ablegen "
            f"(oder --checkpoint / {ENV_VAR} verwenden)."
        ) from e
    os.replace(part, dest)


def ensure_checkpoint(path: Path, progress: Progress | None = None) -> Path:
    if not path.is_file() or path.stat().st_size < MIN_CHECKPOINT_BYTES:
        download_checkpoint(path, progress=progress)
        if path.stat().st_size < MIN_CHECKPOINT_BYTES:
            path.unlink()
            raise ModelDownloadError(f"Heruntergeladene Datei ist zu klein: {path}")
    return path


class ByteDanceTranscriber:
    name = "bytedance"
    version = "0.0.6+note_F1=0.9677"

    def __init__(self, checkpoint: Path | None = None, progress: Progress | None = None):
        self.checkpoint = resolve_checkpoint(checkpoint)
        self.progress = progress
        self._model = None

    def _load_model(self):
        if self._model is None:
            path = ensure_checkpoint(self.checkpoint, self.progress)
            from piano_transcription_inference import PianoTranscription

            # device="cpu" ausdrücklich: Standard des Pakets ist cuda
            self._model = PianoTranscription(device="cpu", checkpoint_path=str(path))
        return self._model

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> NoteList:
        if sample_rate != SAMPLE_RATE:
            raise ValueError(f"ByteDance-Backend erwartet {SAMPLE_RATE} Hz, nicht {sample_rate}")
        out = self._load_model().transcribe(audio, None)
        notes = []
        for e in out["est_note_events"]:
            pitch = int(e["midi_note"])
            onset, offset = float(e["onset_time"]), float(e["offset_time"])
            if PITCH_MIN <= pitch <= PITCH_MAX and offset > onset >= 0:
                velocity = min(max(int(e["velocity"]), 1), 127)
                notes.append(Note(pitch, onset, offset, velocity))
        pedals = [
            PedalEvent(float(e["onset_time"]), float(e["offset_time"]))
            for e in out["est_pedal_events"]
            if float(e["offset_time"]) > float(e["onset_time"]) >= 0
        ]
        return NoteList(notes, pedals, len(audio) / sample_rate, self.name, self.version)
