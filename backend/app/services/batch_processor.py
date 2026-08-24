import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import AudioResult, Batch
from app.pipeline.pipeline import run_pipeline
from app.services.storage import batch_dir, cleanup_batch

logger = logging.getLogger("batch_processor")


def process_batch(batch_id: str) -> None:
    db: Session = SessionLocal()
    try:
        batch = db.query(Batch).filter(Batch.id == batch_id).first()
        if batch is None:
            logger.error("batch %s not found", batch_id)
            return

        try:
            batch.status = "processing"
            db.commit()

            directory = batch_dir(batch_id)
            results = db.query(AudioResult).filter(AudioResult.batch_id == batch_id).all()

            for result in results:
                result.status = "processing"
                db.commit()

                audio_path = directory / result.filename
                try:
                    outcome = run_pipeline(str(audio_path))
                    pred = outcome.prediction
                    result.status = "done"
                    result.emotional_tone = pred.emotional_tone.value
                    result.emotional_intensity = pred.emotional_intensity.value
                    result.background_noise_present = pred.background_noise_present
                    result.background_noise_type = pred.background_noise_type
                    result.background_noise_severity = pred.background_noise_severity.value
                    result.audio_quality = pred.audio_quality.value
                    result.speaker_overlap_present = pred.speaker_overlap_present
                    result.long_silence_present = pred.long_silence_present
                    result.confidence = pred.confidence
                    result.processing_ms = outcome.processing_ms
                    result.audio_duration_seconds = outcome.duration_s
                    batch.processed_files += 1
                except Exception as exc:  # noqa: BLE001 -- one bad file must not fail the batch
                    logger.exception("failed to process %s in batch %s", result.filename, batch_id)
                    result.status = "error"
                    result.error_message = str(exc)[:1000]
                    batch.failed_files += 1

                db.commit()

            batch.status = "completed"
            batch.completed_at = datetime.now(timezone.utc)
            db.commit()
        except Exception:  # noqa: BLE001 -- a batch must never be left stuck in "processing"
            logger.exception("batch %s failed outside per-file processing", batch_id)
            batch.status = "failed"
            db.commit()
    finally:
        cleanup_batch(batch_id)
        db.close()
