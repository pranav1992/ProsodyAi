"""Deterministic acoustic analysis: noise, audio quality, overlap, silence.

Kept independent of any LLM call so these fields are cheap, fast, and fully
reproducible. Thresholds are documented inline; see VALIDATION.md for how
they were chosen against the three labeled calls.
"""
from dataclasses import dataclass, field

import librosa
import numpy as np
import webrtcvad

from app.pipeline.audio_io import TARGET_SR, duration_seconds

FRAME_MS = 30
FRAME_LEN = int(TARGET_SR * FRAME_MS / 1000)
VAD_AGGRESSIVENESS = 2  # 0-3, higher = more aggressive about calling audio speech
LONG_SILENCE_THRESHOLD_S = 4.0
CLIPPING_THRESHOLD = 0.99
CLIPPING_FRACTION_FOR_SEVERE = 0.001


@dataclass
class AcousticFeatures:
    duration_s: float
    speech_ratio: float
    longest_silence_s: float
    long_silence_present: bool
    speaker_overlap_present: bool
    overlap_ratio: float
    snr_db: float
    clipping_fraction: float
    mean_rms_dbfs: float
    spectral_flatness: float
    background_noise_present: bool
    background_noise_severity: str  # none | low | medium | high
    audio_quality: str  # clear | slightly_impaired | severely_impaired
    raw: dict = field(default_factory=dict)


def _frame_generator(audio_i16: np.ndarray):
    n = len(audio_i16) // FRAME_LEN
    for i in range(n):
        yield audio_i16[i * FRAME_LEN:(i + 1) * FRAME_LEN]


def _vad_speech_mask(audio: np.ndarray, sr: int) -> np.ndarray:
    vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)
    audio_i16 = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    mask = []
    for frame in _frame_generator(audio_i16):
        is_speech = vad.is_speech(frame.tobytes(), sr)
        mask.append(is_speech)
    return np.array(mask, dtype=bool)


def _longest_silence_run(speech_mask: np.ndarray) -> float:
    if len(speech_mask) == 0:
        return 0.0
    longest = current = 0
    for is_speech in speech_mask:
        if not is_speech:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest * FRAME_MS / 1000.0


def _estimate_snr_db(audio: np.ndarray, speech_mask: np.ndarray) -> float:
    """Speech-vs-noise-floor SNR from frame RMS, using VAD to separate segments."""
    n_frames = len(speech_mask)
    frame_rms = np.array([
        np.sqrt(np.mean(audio[i * FRAME_LEN:(i + 1) * FRAME_LEN] ** 2) + 1e-12)
        for i in range(n_frames)
    ])
    speech_rms = frame_rms[speech_mask]
    noise_rms = frame_rms[~speech_mask]
    if len(speech_rms) == 0 or len(noise_rms) == 0:
        return 30.0  # not enough data to distinguish; assume clean
    speech_level = np.percentile(speech_rms, 75)
    noise_level = np.percentile(noise_rms, 50)
    snr = 20 * np.log10((speech_level + 1e-9) / (noise_level + 1e-9))
    return float(np.clip(snr, -10, 60))


def _overlap_ratio_mono(audio: np.ndarray, sr: int, speech_mask: np.ndarray) -> float:
    """Heuristic overlap proxy for mono audio: spectral-flatness/harmonic-complexity
    spikes during speech regions suggest two voices talking simultaneously.
    This is a best-effort signal, not true diarization -- see LIMITATIONS in memo.
    """
    if not speech_mask.any():
        return 0.0
    hop = FRAME_LEN
    flatness = librosa.feature.spectral_flatness(y=audio, hop_length=hop, n_fft=hop * 2)[0]
    n = min(len(flatness), len(speech_mask))
    flatness, mask = flatness[:n], speech_mask[:n]
    speech_flatness = flatness[mask]
    if len(speech_flatness) < 5:
        return 0.0
    threshold = np.percentile(speech_flatness, 85)
    complex_frames = np.sum(speech_flatness > threshold)
    return float(complex_frames / max(len(speech_flatness), 1))


def analyze(audio: np.ndarray, sr: int) -> AcousticFeatures:
    dur = duration_seconds(audio, sr)
    speech_mask = _vad_speech_mask(audio, sr)

    speech_ratio = float(speech_mask.mean()) if len(speech_mask) else 0.0
    longest_silence = _longest_silence_run(speech_mask)
    long_silence_present = longest_silence >= LONG_SILENCE_THRESHOLD_S

    snr_db = _estimate_snr_db(audio, speech_mask)
    clipping_fraction = float(np.mean(np.abs(audio) >= CLIPPING_THRESHOLD))
    rms = np.sqrt(np.mean(audio ** 2) + 1e-12)
    mean_rms_dbfs = float(20 * np.log10(rms + 1e-9))
    spectral_flatness = float(np.mean(librosa.feature.spectral_flatness(y=audio)))

    overlap_ratio = _overlap_ratio_mono(audio, sr, speech_mask)
    speaker_overlap_present = overlap_ratio > 0.12

    # Noise presence/severity from SNR: higher SNR = cleaner speech-vs-background gap.
    if snr_db >= 22:
        noise_present, noise_severity = False, "none"
    elif snr_db >= 15:
        noise_present, noise_severity = True, "low"
    elif snr_db >= 8:
        noise_present, noise_severity = True, "medium"
    else:
        noise_present, noise_severity = True, "high"

    # Audio quality from clipping + absolute level, independent of noise/tone.
    if clipping_fraction > CLIPPING_FRACTION_FOR_SEVERE or mean_rms_dbfs < -40:
        audio_quality = "severely_impaired"
    elif clipping_fraction > 0 or mean_rms_dbfs < -30 or snr_db < 10:
        audio_quality = "slightly_impaired"
    else:
        audio_quality = "clear"

    return AcousticFeatures(
        duration_s=dur,
        speech_ratio=speech_ratio,
        longest_silence_s=longest_silence,
        long_silence_present=long_silence_present,
        speaker_overlap_present=speaker_overlap_present,
        overlap_ratio=overlap_ratio,
        snr_db=snr_db,
        clipping_fraction=clipping_fraction,
        mean_rms_dbfs=mean_rms_dbfs,
        spectral_flatness=spectral_flatness,
        background_noise_present=noise_present,
        background_noise_severity=noise_severity,
        audio_quality=audio_quality,
        raw={
            "speech_ratio": speech_ratio,
            "snr_db": snr_db,
            "clipping_fraction": clipping_fraction,
            "mean_rms_dbfs": mean_rms_dbfs,
            "spectral_flatness": spectral_flatness,
            "overlap_ratio": overlap_ratio,
            "longest_silence_s": longest_silence,
        },
    )
