import csv
import io
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models import AudioResult, Batch, User
from app.rate_limit import limiter
from app.schemas import AudioResultOut, BatchDetailOut, BatchOut
from app.services.batch_processor import process_batch
from app.services.storage import (
    UploadTooLargeError,
    cleanup_batch,
    extract_zip,
    find_manifest,
    list_audio_files,
    save_upload_stream,
)
from app.utils.csv_manifest import parse_and_validate

router = APIRouter(prefix="/batches", tags=["batches"])
settings = get_settings()
logger = logging.getLogger(__name__)

RESULT_FIELDS = [
    "emotional_tone", "emotional_intensity", "background_noise_present",
    "background_noise_type", "background_noise_severity", "audio_quality",
    "speaker_overlap_present", "long_silence_present", "confidence",
]


@router.post("", response_model=BatchDetailOut)
@limiter.limit("3/hour;10/day")
async def upload_batch(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile,
    name: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Upload must be a .zip archive containing audio files and a CSV manifest")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    try:
        # Streamed to a temp file one chunk at a time rather than buffered
        # into memory -- on a memory-constrained instance, several large
        # uploads landing at once could otherwise OOM the process.
        tmp_zip_path = await save_upload_stream(file, max_bytes)
    except UploadTooLargeError:
        raise HTTPException(
            status_code=413,
            detail=f"Upload exceeds the {settings.max_upload_mb}MB limit",
        )

    batch = Batch(name=name or file.filename, owner_id=user.id, status="pending")
    db.add(batch)
    db.commit()
    db.refresh(batch)

    try:
        directory = extract_zip(tmp_zip_path, batch.id)
        audio_files = list_audio_files(directory)
        manifest_path = find_manifest(directory)
    except Exception:
        logger.exception("failed to extract uploaded archive for batch %s", batch.id)
        batch.status = "failed"
        db.commit()
        cleanup_batch(batch.id)
        raise HTTPException(status_code=400, detail="Could not read the uploaded archive -- make sure it's a valid .zip file")

    if manifest_path is None:
        batch.status = "failed"
        db.commit()
        raise HTTPException(status_code=400, detail="No CSV manifest found at the root of the uploaded archive")

    validation = parse_and_validate(manifest_path.read_bytes(), audio_files)
    if validation.errors:
        batch.status = "failed"
        db.commit()
        raise HTTPException(status_code=400, detail={"manifest_errors": validation.errors})

    if not validation.matched:
        batch.status = "failed"
        db.commit()
        raise HTTPException(
            status_code=400,
            detail={
                "message": "No audio files matched the manifest",
                "missing_audio": validation.missing_audio,
                "unmatched_files": validation.unmatched_files,
            },
        )

    for filename, expected_json in validation.matched.items():
        db.add(AudioResult(
            batch_id=batch.id,
            filename=filename,
            status="pending",
            expected_json=expected_json or None,
        ))
    batch.total_files = len(validation.matched)
    db.commit()
    db.refresh(batch)

    background_tasks.add_task(process_batch, batch.id)
    logger.info("batch %s queued: %d files, owner %s", batch.id, batch.total_files, user.id)

    out = BatchDetailOut.model_validate(batch)
    return out


@router.get("", response_model=list[BatchOut])
@limiter.limit("30/minute")
def list_batches(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Batch).filter(Batch.owner_id == user.id).order_by(Batch.created_at.desc()).all()


@router.get("/{batch_id}", response_model=BatchDetailOut)
@limiter.limit("30/minute")
def get_batch(request: Request, batch_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    batch = db.query(Batch).filter(Batch.id == batch_id, Batch.owner_id == user.id).first()
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch


@router.delete("/{batch_id}", status_code=204)
@limiter.limit("20/minute")
def delete_batch(request: Request, batch_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    batch = db.query(Batch).filter(Batch.id == batch_id, Batch.owner_id == user.id).first()
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    db.delete(batch)
    db.commit()
    cleanup_batch(batch_id)


def _result_to_dict(r: AudioResult) -> dict:
    return {
        "name": r.filename,
        "status": r.status,
        "error_message": r.error_message,
        "result_json": json.dumps({f: getattr(r, f) for f in RESULT_FIELDS}) if r.status == "done" else "",
    }


@router.get("/{batch_id}/download")
@limiter.limit("5/minute")
def download_results(
    request: Request,
    batch_id: str,
    format: str = "csv",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    batch = db.query(Batch).filter(Batch.id == batch_id, Batch.owner_id == user.id).first()
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")

    results = db.query(AudioResult).filter(AudioResult.batch_id == batch_id).all()

    if format == "json":
        payload = [
            {"name": r.filename, "status": r.status, "error_message": r.error_message,
             **{f: getattr(r, f) for f in RESULT_FIELDS}}
            for r in results
        ]
        content = json.dumps(payload, indent=2)
        return StreamingResponse(
            io.BytesIO(content.encode()),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{batch_id}_results.json"'},
        )

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["name", "status", "error_message", "result_json"])
    writer.writeheader()
    for r in results:
        writer.writerow(_result_to_dict(r))
    return StreamingResponse(
        io.BytesIO(buffer.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{batch_id}_results.csv"'},
    )
