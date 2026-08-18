import numpy as np

from app.pipeline.acoustic_features import analyze

SR = 16000


def test_duration_matches_input_length():
    audio = np.zeros(SR * 5, dtype=np.float32)  # 5 seconds of silence
    features = analyze(audio, SR)
    assert abs(features.duration_s - 5.0) < 0.1


def test_pure_silence_is_flagged_as_long_silence():
    audio = np.zeros(SR * 6, dtype=np.float32)
    features = analyze(audio, SR)
    assert features.long_silence_present is True
    assert features.speech_ratio == 0.0


def test_clipped_signal_is_severely_impaired():
    t = np.linspace(0, 3, SR * 3, endpoint=False)
    tone = 2.0 * np.sin(2 * np.pi * 220 * t)  # amplitude > 1 forces clipping on write
    audio = np.clip(tone, -1.0, 1.0).astype(np.float32)
    features = analyze(audio, SR)
    assert features.clipping_fraction > 0
    assert features.audio_quality == "severely_impaired"


def test_low_level_signal_is_impaired_not_clear():
    t = np.linspace(0, 3, SR * 3, endpoint=False)
    quiet_tone = (0.005 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    features = analyze(quiet_tone, SR)
    assert features.audio_quality != "clear"
