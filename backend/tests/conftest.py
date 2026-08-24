import io
import os
import tempfile
import zipfile

# Must happen before any `app.*` import: app/config.py reads env vars into
# class attributes at import time, so setting them later has no effect.
_TEST_DB = tempfile.NamedTemporaryFile(prefix="autoace_test_", suffix=".db", delete=False)
_TEST_STORAGE_DIR = tempfile.mkdtemp(prefix="autoace_test_storage_")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB.name}"
os.environ["STORAGE_DIR"] = _TEST_STORAGE_DIR
os.environ["JWT_SECRET"] = "test-secret"
os.environ["ADMIN_EMAIL"] = "admin@autoace.ai"
os.environ["ADMIN_PASSWORD"] = "changeme123"
os.environ["OPENAI_API_KEY"] = "sk-test-not-real"

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import Base, engine
from app.main import app
from app.rate_limit import limiter

settings = get_settings()


@pytest.fixture
def client():
    Base.metadata.drop_all(bind=engine)
    limiter.reset()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers(client):
    resp = client.post(
        "/auth/login",
        json={"email": settings.admin_email, "password": settings.admin_password},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def build_zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for filename, content in files.items():
            zf.writestr(filename, content)
    return buffer.getvalue()


def valid_batch_zip() -> bytes:
    return build_zip({
        "manifest.csv": b"name,result_json\ncall_001.wav,\n",
        "call_001.wav": b"fake-audio-bytes",
    })
