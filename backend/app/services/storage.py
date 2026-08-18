import shutil
import zipfile
from pathlib import Path

from app.config import get_settings

settings = get_settings()

SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".flac"}


def batch_dir(batch_id: str) -> Path:
    path = Path(settings.storage_dir) / batch_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def extract_zip(zip_bytes: bytes, batch_id: str) -> Path:
    target = batch_dir(batch_id)
    zip_path = target / "_upload.zip"
    zip_path.write_bytes(zip_bytes)

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
