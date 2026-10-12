import tempfile
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from audio2score.model import PITCH_MAX, PITCH_MIN, Note, NoteList
from audio2score.transcribe.base import BackendUnavailableError

SAMPLE_RATE = 16_000
_MODEL_SR = 22_050  # Basic Pitch arbeitet intern mit 22,05 kHz

INSTALL_HINT = (
    "Das Backend 'basic-pitch' ist nicht installiert. Installation:\n"
    "  pip install -e .[basic-pitch]\n"
    "  pip install --no-deps basic-pitch==0.4.0"
)


class BasicPitchTranscriber:
    name = "basic-pitch"
    version = "0.4.0-onnx"

    def _predict(self, wav_path: Path):
        try:
            from basic_pitch import FilenameSuffix, build_icassp_2022_model_path
            from basic_pitch.inference import predict
        except ImportError as e:
            raise BackendUnavailableError(f"{INSTALL_HINT}\n({e})") from e
        model = build_icassp_2022_model_path(FilenameSuffix.onnx)
        return predict(str(wav_path), model_or_model_path=model)

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> NoteList:
        if sample_rate != SAMPLE_RATE:
            raise ValueError(f"Basic-Pitch-Backend erwartet {SAMPLE_RATE} Hz, nicht {sample_rate}")
        resampled = librosa.resample(audio, orig_sr=sample_rate, target_sr=_MODEL_SR)
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "audio.wav"
            sf.write(wav, resampled, _MODEL_SR)
            _, _, events = self._predict(wav)
        notes = []
        for start, end, pitch, amplitude, _bends in events:
            pitch = int(pitch)
            if PITCH_MIN <= pitch <= PITCH_MAX and float(end) > float(start) >= 0:
                velocity = min(max(round(float(amplitude) * 127), 1), 127)
                notes.append(Note(pitch, float(start), float(end), velocity))
        return NoteList(notes, [], len(audio) / sample_rate, self.name, self.version)
