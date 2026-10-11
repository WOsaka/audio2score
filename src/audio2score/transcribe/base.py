from typing import Protocol

import numpy as np

from audio2score.model import NoteList


class BackendUnavailableError(Exception):
    """Backend nicht nutzbar, z. B. weil ein Extra fehlt (mit Installationshinweis)."""


class ModelDownloadError(Exception):
    pass


class Transcriber(Protocol):
    name: str
    version: str  # fließt in den Cache-Schlüssel ein

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> NoteList: ...
