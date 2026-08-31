from app.auth import hash_password
from app.database import SessionLocal
from app.models import AudioResult, Batch, User
from app.pipeline.errors import ClassificationServiceError
from app.pipeline.pipeline import PipelineResult
from app.schemas import (
    AudioQuality,
    EmotionalIntensity,
    EmotionalTone,
    NoiseSeverity,
    PredictionResult,
)
from app.services.batch_processor import process_batch


def _fake_pipeline_result() -> PipelineResult:
    prediction = PredictionResult(
        emotional_tone=EmotionalTone.neutral,
        emotional_intensity=EmotionalIntensity.low,
        background_noise_present=False,
        background_noise_type="",
        background_noise_severity=NoiseSeverity.none,
        audio_quality=AudioQuality.clear,
        speaker_overlap_present=False,
        long_silence_present=False,
        confidence=0.9,
    )
    return PipelineResult(prediction=prediction, duration_s=3.0, processing_ms=123, debug={})


def _seed_batch(num_files: int = 1) -> str:
    db = SessionLocal()
    try:
        user = User(email="pipeline-test@example.com", hashed_password=hash_password("x"))
        db.add(user)
        db.commit()
        db.refresh(user)

        batch = Batch(name="test-batch", owner_id=user.id, status="pending", total_files=num_files)
        db.add(batch)
        db.commit()
        db.refresh(batch)

        for i in range(num_files):
            db.add(AudioResult(batch_id=batch.id, filename=f"call_{i}.wav", status="pending"))
        db.commit()
        return batch.id
    finally:
        db.close()


def _get_batch(batch_id: str) -> Batch:
    db = SessionLocal()
    try:
        return db.query(Batch).filter(Batch.id == batch_id).first()
    finally:
        db.close()


def test_process_batch_marks_completed_on_success(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.batch_processor.run_pipeline",
        lambda audio_path: _fake_pipeline_result(),
    )
    batch_id = _seed_batch(num_files=1)

    process_batch(batch_id)

    batch = _get_batch(batch_id)
    assert batch.status == "completed"
    assert batch.processed_files == 1
    assert batch.failed_files == 0
    assert batch.completed_at is not None


def test_process_batch_marks_file_error_but_batch_still_completes(client, monkeypatch):
    def _boom(audio_path):
        raise RuntimeError("ffmpeg blew up")

    monkeypatch.setattr("app.services.batch_processor.run_pipeline", _boom)
    batch_id = _seed_batch(num_files=1)

    process_batch(batch_id)

    batch = _get_batch(batch_id)
    assert batch.status == "completed"  # one bad file must not fail the whole batch
    assert batch.processed_files == 0
    assert batch.failed_files == 1

    db = SessionLocal()
    try:
        result = db.query(AudioResult).filter(AudioResult.batch_id == batch_id).first()
        assert result.status == "error"
        assert "ffmpeg blew up" in result.error_message
    finally:
        db.close()


def test_process_batch_marks_batch_failed_on_error_outside_per_file_loop(client, monkeypatch):
    def _boom(batch_id):
        raise RuntimeError("disk unavailable")

    # forces a failure before the per-file loop even starts
    monkeypatch.setattr("app.services.batch_processor.batch_dir", _boom)
    batch_id = _seed_batch(num_files=1)

    process_batch(batch_id)

    batch = _get_batch(batch_id)
    assert batch.status == "failed"


def test_process_batch_handles_missing_batch_gracefully(client):
    # must not raise even if the batch row doesn't exist
    process_batch("does-not-exist")


def test_process_batch_aborts_remaining_files_on_classification_service_error(client, monkeypatch):
    call_count = 0

    def _quota_exhausted(audio_path):
        nonlocal call_count
        call_count += 1
        raise ClassificationServiceError("OpenAI account has run out of credits.")

    monkeypatch.setattr("app.services.batch_processor.run_pipeline", _quota_exhausted)
    batch_id = _seed_batch(num_files=3)

    process_batch(batch_id)

    # fail-fast: run_pipeline (which transcribes before classifying) should
    # only run once, not once per file -- the whole point is not to burn
    # compute on files guaranteed to fail the same way.
    assert call_count == 1

    batch = _get_batch(batch_id)
    assert batch.status == "failed"  # systemic failure, not per-file
    assert batch.processed_files == 0
    assert batch.failed_files == 3

    db = SessionLocal()
    try:
        results = db.query(AudioResult).filter(AudioResult.batch_id == batch_id).all()
        assert len(results) == 3
        for result in results:
            assert result.status == "error"
            assert result.error_message == "OpenAI account has run out of credits."
    finally:
        db.close()
