from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class EmotionalTone(str, Enum):
    neutral = "neutral"
    satisfied = "satisfied"
    frustrated = "frustrated"
    upset = "upset"
    distressed = "distressed"


class EmotionalIntensity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class NoiseSeverity(str, Enum):
    none = "none"
    low = "low"
    medium = "medium"
    high = "high"


class AudioQuality(str, Enum):
    clear = "clear"
    slightly_impaired = "slightly_impaired"
    severely_impaired = "severely_impaired"


class PredictionResult(BaseModel):
    emotional_tone: EmotionalTone
    emotional_intensity: EmotionalIntensity
    background_noise_present: bool
    background_noise_type: str = ""
    background_noise_severity: NoiseSeverity
    audio_quality: AudioQuality
    speaker_overlap_present: bool
    long_silence_present: bool
    confidence: float = Field(ge=0.0, le=1.0)


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class BatchOut(BaseModel):
    id: str
    name: str
    status: str
    total_files: int
    processed_files: int
    failed_files: int
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AudioResultOut(BaseModel):
    id: str
    filename: str
    status: str
    error_message: Optional[str] = None
    emotional_tone: Optional[str] = None
    emotional_intensity: Optional[str] = None
    background_noise_present: Optional[bool] = None
    background_noise_type: Optional[str] = None
    background_noise_severity: Optional[str] = None
    audio_quality: Optional[str] = None
    speaker_overlap_present: Optional[bool] = None
    long_silence_present: Optional[bool] = None
    confidence: Optional[float] = None
    processing_ms: Optional[int] = None
    audio_duration_seconds: Optional[float] = None

    class Config:
        from_attributes = True


class BatchDetailOut(BatchOut):
    results: list[AudioResultOut] = []
