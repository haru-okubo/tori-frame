"""Audio loading and windowing for Perch v2 (32 kHz mono, 5 s)."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import resampy
import soundfile as sf

SAMPLE_RATE = 32_000
WINDOW_SAMPLES = 5 * SAMPLE_RATE  # 160_000

# Formats libsndfile may not open (phone recordings); decode via ffmpeg.
_FFMPEG_SUFFIXES = {".m4a", ".mp3", ".aac", ".mp4", ".3gp", ".amr", ".wma", ".opus", ".webm"}


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _load_via_ffmpeg(path: Path, target_sr: int) -> np.ndarray:
    if not _ffmpeg_available():
        raise RuntimeError(
            f"Cannot decode {path.suffix} without ffmpeg. Install ffmpeg or convert to WAV."
        )
    # Decode to float32 mono PCM WAV on stdout via temp file (reliable length).
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(path),
            "-ac",
            "1",
            "-ar",
            str(target_sr),
            "-f",
            "wav",
            str(tmp_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"ffmpeg failed for {path}: {proc.stderr[-500:] if proc.stderr else 'unknown'}"
            )
        audio, sr = sf.read(tmp_path, always_2d=True, dtype="float32")
        mono = audio.mean(axis=1)
        if sr != target_sr:
            mono = resampy.resample(mono, sr, target_sr).astype(np.float32)
        return mono
    finally:
        tmp_path.unlink(missing_ok=True)


def load_mono(path: str | Path, target_sr: int = SAMPLE_RATE) -> np.ndarray:
    """Load audio as float32 mono in [-1, 1], resampled to target_sr.

    Supports WAV/FLAC/OGG via soundfile, and phone formats (m4a/mp3/aac/…)
    via ffmpeg when installed.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower()
    if suffix in _FFMPEG_SUFFIXES:
        return _load_via_ffmpeg(path, target_sr)
    try:
        audio, sr = sf.read(path, always_2d=True, dtype="float32")
    except Exception:
        # Some .wav containers still need ffmpeg; fall through.
        return _load_via_ffmpeg(path, target_sr)
    mono = audio.mean(axis=1)
    if sr != target_sr:
        mono = resampy.resample(mono, sr, target_sr).astype(np.float32)
    return mono


def iter_windows(
    waveform: np.ndarray,
    window_samples: int = WINDOW_SAMPLES,
    hop_samples: int | None = None,
) -> list[tuple[float, np.ndarray]]:
    """Return list of (start_sec, window) covering the waveform.

    Short files are zero-padded to one window. hop defaults to window
    length (non-overlapping); use hop_samples=window//2 for 50% overlap.
    """
    if hop_samples is None:
        hop_samples = window_samples
    if waveform.size == 0:
        return []
    if waveform.size < window_samples:
        padded = np.zeros(window_samples, dtype=np.float32)
        padded[: waveform.size] = waveform
        return [(0.0, padded)]

    out: list[tuple[float, np.ndarray]] = []
    start = 0
    while start + window_samples <= waveform.size:
        w = waveform[start : start + window_samples].astype(np.float32, copy=False)
        out.append((start / SAMPLE_RATE, w))
        start += hop_samples
    # If last hop left a remainder longer than 1 s, pad one more window from end
    last_end = (out[-1][0] * SAMPLE_RATE) + window_samples if out else 0
    if waveform.size - last_end >= SAMPLE_RATE:
        chunk = waveform[-window_samples:]
        if chunk.size < window_samples:
            padded = np.zeros(window_samples, dtype=np.float32)
            padded[-chunk.size :] = chunk
            chunk = padded
        out.append(((waveform.size - window_samples) / SAMPLE_RATE, chunk.astype(np.float32)))
    return out
