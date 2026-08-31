import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Protocol

from app.config import get_settings

settings = get_settings()

SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".flac"}

UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1MB


class UploadTooLargeError(Exception):
    def __init__(self, total_bytes: int):
        self.total_bytes = total_bytes


class _ChunkedUpload(Protocol):
    async def read(self, size: int) -> bytes: ...


def batch_dir(batch_id: str) -> Path:
    path = Path(settings.storage_dir) / batch_id
    path.mkdir(parents=True, exist_ok=True)
    return path


async def save_upload_stream(file: _ChunkedUpload, max_bytes: int) -> Path:
    """Write an uploaded file to a temp path one chunk at a time, enforcing
    max_bytes as it goes. Never holds the full upload in memory at once --
    unlike buffering into a list and `b"".join(...)`-ing it, which on a
    memory-constrained instance risks OOM if several large uploads land
    around the same time (see README's Scaling plan)."""
    Path(settings.storage_dir).mkdir(parents=True, exist_ok=True)
    fd, tmp_path_str = tempfile.mkstemp(suffix=".zip", dir=settings.storage_dir)
    tmp_path = Path(tmp_path_str)
    total_size = 0
    try:
        with open(fd, "wb") as f:
            while chunk := await file.read(UPLOAD_CHUNK_SIZE):
                total_size += len(chunk)
                if total_size > max_bytes:
                    raise UploadTooLargeError(total_size)
                f.write(chunk)
        return tmp_path
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def extract_zip(zip_path: Path, batch_id: str) -> Path:
    target = batch_dir(batch_id)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for member in zf.namelist():
                # flatten to folder root regardless of zip internal folder nesting,
                # per the brief's "audio files at the folder root" requirement
                member_path = Path(member)
                if member_path.name == "" or member.startswith("__MACOSX"):
                    continue
                dest = target / member_path.name
                with zf.open(member) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)
    finally:
        zip_path.unlink(missing_ok=True)
    return target


def list_audio_files(directory: Path) -> set[str]:
    return {
        p.name for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
    }


def find_manifest(directory: Path) -> Path | None:
    csv_files = list(directory.glob("*.csv"))
    return csv_files[0] if csv_files else None


def cleanup_batch(batch_id: str) -> None:
    """Delete raw audio after processing -- confidential production-call audio
    should not persist longer than needed to produce results. See MEMO.md."""
    path = Path(settings.storage_dir) / batch_id
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
