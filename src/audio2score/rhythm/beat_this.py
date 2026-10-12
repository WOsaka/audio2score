from importlib import metadata

import numpy as np

from audio2score.rhythm.base import Beats
from audio2score.transcribe.base import BackendUnavailableError, ModelDownloadError

SAMPLE_RATE = 22_050
CHECKPOINT = "final0"
INSTALL_HINT = "beat_this fehlt. Installation: pip install beat_this torchaudio"


def _package_version() -> str:
    try:
        return metadata.version("beat_this")
    except metadata.PackageNotFoundError:
        return "unknown"


class BeatThisTracker:
    """Beats und Downbeats mit `beat_this` (CPU, ohne DBN – das bräuchte madmom)."""

    name = "beat_this"

    def __init__(self) -> None:
        self.version = f"{_package_version()}-{CHECKPOINT}"
        self._model = None

    def _load(self):
        try:
            from beat_this.inference import Audio2Beats
        except ImportError as e:
            raise BackendUnavailableError(INSTALL_HINT) from e
        try:
            return Audio2Beats(checkpoint_path=CHECKPOINT, device="cpu", dbn=False)
        except Exception as e:  # Netz-, Datei- oder Formatfehler beim Laden der Gewichte
            raise ModelDownloadError(
                f"Gewichte '{CHECKPOINT}' für beat_this konnten nicht geladen werden ({e})."
            ) from e

    def track(self, audio: np.ndarray, sample_rate: int) -> Beats:
        if sample_rate != SAMPLE_RATE:
            raise ValueError(f"beat_this erwartet {SAMPLE_RATE} Hz, nicht {sample_rate}")
        if self._model is None:
            self._model = self._load()
        beats, downbeats = self._model(audio, sample_rate)
        times = [float(t) for t in beats]
        return Beats(times, _snap(times, downbeats), self.name, self.version)


def _snap(times: list[float], downbeats) -> list[float]:
    """Downbeats auf den nächsten Beat einrasten; Dubletten fallen weg."""
    if not times:
        return []
    arr = np.asarray(times)
    snapped = {int(np.abs(arr - float(d)).argmin()) for d in downbeats}
    return [times[i] for i in sorted(snapped)]
