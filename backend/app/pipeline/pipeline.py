import time
from dataclasses import asdict

from app.pipeline.acoustic_features import analyze
from app.pipeline.audio_io import load_mono_16k
from app.pipeline.classify import classify
from app.pipeline.transcribe import transcribe
from app.schemas import PredictionResult


class PipelineResult:
    def __init__(self, prediction: PredictionResult, duration_s: float, processing_ms: int, debug: dict):
        self.prediction = prediction
        self.duration_s = duration_s
        self.processing_ms = processing_ms
        self.debug = debug


def run_pipeline(audio_path: str) -> PipelineResult:
    start = time.monotonic()

    audio, sr = load_mono_16k(audio_path)
    features = analyze(audio, sr)
    transcript = transcribe(audio, sr)
    llm_result, llm_usage = classify(transcript, features)

    prediction = PredictionResult(
        emotional_tone=llm_result["emotional_tone"],
        emotional_intensity=llm_result["emotional_intensity"],
        background_noise_present=features.background_noise_present,
        background_noise_type=llm_result["background_noise_type"] if features.background_noise_present else "",
        background_noise_severity=features.background_noise_severity,
        audio_quality=features.audio_quality,
        speaker_overlap_present=features.speaker_overlap_present,
        long_silence_present=features.long_silence_present,
        confidence=float(llm_result["confidence"]),
    )

    elapsed_ms = int((time.monotonic() - start) * 1000)
    return PipelineResult(
        prediction=prediction,
        duration_s=features.duration_s,
        processing_ms=elapsed_ms,
        debug={"transcript": transcript, "acoustic_features": asdict(features), "llm_usage": llm_usage},
    )
