import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import AudioResult, Batch
from app.pipeline.errors import ClassificationServiceError
from app.pipeline.pipeline import run_pipeline
from app.services.storage import batch_dir, cleanup_batch

logger = logging.getLogger(__name__)
settings = get_settings()

# Batches run on a background thread (FastAPI BackgroundTasks -> anyio
# threadpool), not the asyncio event loop, so this needs a real
# threading.Semaphore -- an asyncio.Semaphore wouldn't coordinate across
# worker threads correctly. Caps concurrent CPU-bound transcription jobs
# to what the instance can actually run without thrashing (see README's
# Scaling plan); batches beyond the cap simply wait in "pending" for a
# slot, which the dashboard already renders correctly.
_processing_semaphore = threading.Semaphore(settings.max_concurrent_batches)


def process_batch(batch_id: str) -> None:
    with _processing_semaphore:
        _process_batch_locked(batch_id)


def _process_batch_locked(batch_id: str) -> None:
    db: Session = SessionLocal()
    try:
        batch = db.query(Batch).filter(Batch.id == batch_id).first()
        if batch is None:
            logger.error("batch %s not found", batch_id)
            return

        try:
            batch.status = "processing"
            db.commit()
            logger.info("batch %s started: %d files", batch_id, batch.total_files)

            directory = batch_dir(batch_id)
            results = db.query(AudioResult).filter(AudioResult.batch_id == batch_id).all()
            service_failure: str | None = None

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
                    logger.info(
                        "batch %s: processed %s in %dms", batch_id, result.filename, outcome.processing_ms
                    )
                except ClassificationServiceError as exc:
                    # Not a per-file problem -- the classification service itself
                    # is unavailable (quota exhausted, bad API key, OpenAI outage).
                    # Every remaining file would fail transcription for nothing, so
                    # stop here instead of grinding through the rest of the batch.
                    logger.error(
                        "batch %s: classification service failure on %s, aborting "
                        "remaining files: %s",
                        batch_id, result.filename, exc.user_message,
                    )
                    result.status = "error"
                    result.error_message = exc.user_message
                    batch.failed_files += 1
                    service_failure = exc.user_message
                    db.commit()
                    break
                except Exception as exc:  # noqa: BLE001 -- one bad file must not fail the batch
                    logger.exception("failed to process %s in batch %s", result.filename, batch_id)
                    result.status = "error"
                    result.error_message = str(exc)[:1000]
                    batch.failed_files += 1

                db.commit()

            if service_failure:
                for r in results:
                    if r.status == "pending":
                        r.status = "error"
                        r.error_message = service_failure
                        batch.failed_files += 1
                batch.status = "failed"
            else:
                batch.status = "completed"
            batch.completed_at = datetime.now(timezone.utc)
            db.commit()
            logger.info(
                "batch %s %s: %d processed, %d failed",
                batch_id, batch.status, batch.processed_files, batch.failed_files,
            )
        except Exception:  # noqa: BLE001 -- a batch must never be left stuck in "processing"
            logger.exception("batch %s failed outside per-file processing", batch_id)
            batch.status = "failed"
            db.commit()
    finally:
        cleanup_batch(batch_id)
        db.close()
