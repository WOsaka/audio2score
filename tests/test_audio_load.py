import shutil
import subprocess

import numpy as np
import pytest
import soundfile as sf

from audio2score.audio.load import SAMPLE_RATE, AudioLoadError, find_ffmpeg, load_audio


def test_stereo_44k_becomes_mono_16k(make_wav):
    y = load_audio(make_wav())
    assert y.dtype == np.float32
    assert y.ndim == 1
    assert len(y) == pytest.approx(SAMPLE_RATE, abs=2)


def test_peak_normalized_to_minus_one_dbfs(make_wav):
    y = load_audio(make_wav(amp=0.1))
    assert np.abs(y).max() == pytest.approx(10 ** (-1 / 20), rel=1e-3)


def test_silence_not_normalized(tmp_path):
    path = tmp_path / "s.wav"
    sf.write(path, np.zeros(16_000, dtype=np.float32), 16_000)
    y = load_audio(path)
    assert np.abs(y).max() == 0.0


def test_flac(make_wav):
    y = load_audio(make_wav("a.flac"))
    assert len(y) == pytest.approx(SAMPLE_RATE, abs=2)


def test_mono_16k_passthrough_length(make_wav):
    y = load_audio(make_wav(sr=16_000, channels=1, dur=2.0))
    assert len(y) == 2 * SAMPLE_RATE


def test_missing_file(tmp_path):
    with pytest.raises(AudioLoadError, match="nicht gefunden"):
        load_audio(tmp_path / "nope.wav")


def test_unreadable_file(tmp_path):
    path = tmp_path / "bad.wav"
    path.write_bytes(b"das ist kein audio")
    with pytest.raises(AudioLoadError):
        load_audio(path)


def test_find_ffmpeg_returns_existing_binary():
    exe = find_ffmpeg()
    assert exe is not None
    assert shutil.which(exe) or __import__("pathlib").Path(exe).exists()


def test_mp3_and_m4a_via_ffmpeg(make_wav, tmp_path):
    ffmpeg = find_ffmpeg()
    src = make_wav()
    for ext in ("mp3", "m4a"):
        out = tmp_path / f"out.{ext}"
        r = subprocess.run([ffmpeg, "-y", "-i", str(src), str(out)], capture_output=True)
        if r.returncode != 0:
            pytest.skip(f"ffmpeg kann {ext} nicht erzeugen")
        y = load_audio(out)
        assert len(y) == pytest.approx(SAMPLE_RATE, rel=0.1)
        assert np.abs(y).max() > 0.5


def test_no_ffmpeg_gives_clear_error(tmp_path, monkeypatch):
    path = tmp_path / "x.m4a"
    path.write_bytes(b"\x00" * 100)
    monkeypatch.setattr("audio2score.audio.load.find_ffmpeg", lambda: None)
    with pytest.raises(AudioLoadError, match="ffmpeg"):
        load_audio(path)
