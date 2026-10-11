import shutil
import subprocess
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

SAMPLE_RATE = 16_000
_PEAK = 10 ** (-1 / 20)  # -1 dBFS
_SILENCE = 1e-6


class AudioLoadError(Exception):
    pass


def find_ffmpeg() -> str | None:
    """ffmpeg im PATH, sonst die Binärdatei aus imageio-ffmpeg."""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        return None


def _load_soundfile(path: Path, sr: int) -> np.ndarray:
    data, file_sr = sf.read(path, dtype="float32", always_2d=True)
    y = data.mean(axis=1)
    if file_sr != sr:
        y = librosa.resample(y, orig_sr=file_sr, target_sr=sr)
    return y


def _load_ffmpeg(path: Path, sr: int) -> np.ndarray:
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        raise AudioLoadError(
            f"{path.name} kann nicht direkt gelesen werden und ffmpeg wurde nicht gefunden. "
            "Bitte ffmpeg installieren (https://ffmpeg.org) oder das Paket imageio-ffmpeg."
        )
    cmd = [ffmpeg, "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        detail = proc.stderr.decode(errors="replace").strip().splitlines()
        raise AudioLoadError(
            f"{path.name} konnte nicht decodiert werden: {detail[-1] if detail else 'keine Daten'}"
        )
    return np.frombuffer(proc.stdout, dtype="<f4").copy()


def load_audio(path: Path, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Lädt Audio als float32, mono, Rate `sr`, Peak -1 dBFS (Stille bleibt Stille)."""
    path = Path(path)
    if not path.is_file():
        raise AudioLoadError(f"Datei nicht gefunden: {path}")
    try:
        y = _load_soundfile(path, sr)
    except (sf.LibsndfileError, RuntimeError):
        y = _load_ffmpeg(path, sr)
    peak = float(np.abs(y).max()) if len(y) else 0.0
    if peak > _SILENCE:
        y = y * (_PEAK / peak)
    return y.astype(np.float32, copy=False)
