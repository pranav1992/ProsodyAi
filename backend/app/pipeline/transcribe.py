"""Self-hosted transcription via faster-whisper.

Runs locally (CPU by default) so no per-minute API cost is incurred and no
raw audio is sent to a third party -- only the resulting transcript text is
later sent to the classification model. See COST.md and MEMO.md.
"""
from functools import lru_cache

import numpy as np
from faster_whisper import WhisperModel

from app.config import get_settings

settings = get_settings()


@lru_cache
def _get_model() -> WhisperModel:
    return WhisperModel(
        settings.whisper_model_size,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )


def transcribe(audio: np.ndarray, sr: int) -> str:
    model = _get_model()
    segments, _info = model.transcribe(audio, language="en", vad_filter=True)
    return " ".join(segment.text.strip() for segment in segments).strip()
