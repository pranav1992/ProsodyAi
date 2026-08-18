import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=_now)

    batches = relationship("Batch", back_populates="owner")


class Batch(Base):
    __tablename__ = "batches"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)
    status = Column(String, default="pending")  # pending | processing | completed | failed
    total_files = Column(Integer, default=0)
    processed_files = Column(Integer, default=0)
    failed_files = Column(Integer, default=0)
    created_at = Column(DateTime, default=_now)
    completed_at = Column(DateTime, nullable=True)

    owner = relationship("User", back_populates="batches")
    results = relationship("AudioResult", back_populates="batch", cascade="all, delete-orphan")


class AudioResult(Base):
    __tablename__ = "audio_results"

    id = Column(String, primary_key=True, default=_uuid)
    batch_id = Column(String, ForeignKey("batches.id"), nullable=False)
    filename = Column(String, nullable=False)
    status = Column(String, default="pending")  # pending | processing | done | error
    error_message = Column(Text, nullable=True)

    # required output schema, flattened
    emotional_tone = Column(String, nullable=True)
    emotional_intensity = Column(String, nullable=True)
    background_noise_present = Column(Boolean, nullable=True)
    background_noise_type = Column(String, nullable=True)
    background_noise_severity = Column(String, nullable=True)
    audio_quality = Column(String, nullable=True)
    speaker_overlap_present = Column(Boolean, nullable=True)
    long_silence_present = Column(Boolean, nullable=True)
    confidence = Column(Float, nullable=True)

    expected_json = Column(Text, nullable=True)  # ground truth from manifest, if provided
    processing_ms = Column(Integer, nullable=True)
    audio_duration_seconds = Column(Float, nullable=True)
    created_at = Column(DateTime, default=_now)

    batch = relationship("Batch", back_populates="results")