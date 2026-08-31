import os
from functools import lru_cache


class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./autoace.db")
    jwt_secret: str = os.getenv("JWT_SECRET", "change-me-in-production")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))

    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    classification_model: str = os.getenv("CLASSIFICATION_MODEL", "gpt-4o-mini")

    whisper_model_size: str = os.getenv("WHISPER_MODEL_SIZE", "base")
    whisper_device: str = os.getenv("WHISPER_DEVICE", "cpu")
    whisper_compute_type: str = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

    storage_dir: str = os.getenv("STORAGE_DIR", "./storage")
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "200"))
    max_concurrent_batches: int = int(os.getenv("MAX_CONCURRENT_BATCHES", "2"))
    max_concurrent_uploads: int = int(os.getenv("MAX_CONCURRENT_UPLOADS", "4"))

    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    admin_email: str = os.getenv("ADMIN_EMAIL", "admin@autoace.ai")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "changeme123")

    cors_origins: list[str] = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")


@lru_cache
def get_settings() -> Settings:
    return Settings()
