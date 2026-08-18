import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

TARGET_SR = 16000


def load_mono_16k(path: str) -> tuple[np.ndarray, int]:
    """Load any input audio format as mono float32 PCM at 16kHz via ffmpeg.

    ffmpeg handles wav/mp3/m4a/ogg/etc uniformly so we don't depend on
    format-specific decoders that vary in codec support across platforms.
    """
    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        cmd = [
            "ffmpeg", "-y", "-i", str(path),
            "-ac", "1", "-ar", str(TARGET_SR), "-f", "wav", tmp.name,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise ValueError(f"ffmpeg failed to decode {Path(path).name}: {result.stderr[-500:]}")
        audio, sr = sf.read(tmp.name, dtype="float32")
    return audio, sr


def duration_seconds(audio: np.ndarray, sr: int) -> float:
    return len(audio) / float(sr)
