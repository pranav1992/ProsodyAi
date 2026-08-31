import asyncio
from pathlib import Path

import pytest

from app.config import get_settings
from app.services.storage import UploadTooLargeError, save_upload_stream


class _FakeUploadFile:
    """Minimal stand-in for FastAPI's UploadFile -- just needs an async
    read(size) that returns chunks then b"" at EOF, like the real thing."""

    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0

    async def read(self, size: int) -> bytes:
        chunk = self._data[self._pos : self._pos + size]
        self._pos += len(chunk)
        return chunk


def test_save_upload_stream_writes_full_content_to_disk():
    content = b"a" * 5000
    tmp_path = asyncio.run(save_upload_stream(_FakeUploadFile(content), max_bytes=10_000))

    try:
        assert Path(tmp_path).read_bytes() == content
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_save_upload_stream_rejects_oversized_upload_and_cleans_up():
    content = b"a" * 20_000
    storage_dir = Path(get_settings().storage_dir)
    storage_dir.mkdir(parents=True, exist_ok=True)
    before = set(storage_dir.iterdir())

    with pytest.raises(UploadTooLargeError) as exc_info:
        asyncio.run(save_upload_stream(_FakeUploadFile(content), max_bytes=10_000))

    assert exc_info.value.total_bytes > 10_000

    after = set(storage_dir.iterdir())
    assert after == before  # the partial temp file must not be left behind
