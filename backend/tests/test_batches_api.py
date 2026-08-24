import io
import zipfile

from app.auth import hash_password
from app.database import SessionLocal
from app.models import Batch, User

from conftest import build_zip, valid_batch_zip


def _mock_process_batch(monkeypatch):
    """Batch upload backgrounds real Whisper/OpenAI processing -- irrelevant
    to these API/validation-layer tests, and neither is available in CI."""
    monkeypatch.setattr("app.routes.batches.process_batch", lambda batch_id: None)


def test_upload_rejects_non_zip_extension(client, auth_headers):
    resp = client.post(
        "/batches",
        headers=auth_headers,
        files={"file": ("call.wav", b"not a zip", "audio/wav")},
    )
    assert resp.status_code == 400
    assert "zip" in resp.json()["detail"].lower()


def test_upload_rejects_oversized_file(client, auth_headers, monkeypatch):
    import app.routes.batches as batches_module
    monkeypatch.setattr(batches_module.settings, "max_upload_mb", 1)

    oversized = b"0" * (2 * 1024 * 1024)  # 2MB against a 1MB limit
    resp = client.post(
        "/batches",
        headers=auth_headers,
        files={"file": ("big.zip", oversized, "application/zip")},
    )
    assert resp.status_code == 413
    assert "1MB" in resp.json()["detail"]


def test_upload_rejects_corrupt_zip_and_marks_batch_failed(client, auth_headers):
    resp = client.post(
        "/batches",
        headers=auth_headers,
        files={"file": ("corrupt.zip", b"this is not a real zip file", "application/zip")},
    )
    assert resp.status_code == 400
    assert "valid .zip" in resp.json()["detail"]

    batches = client.get("/batches", headers=auth_headers).json()
    assert len(batches) == 1
    assert batches[0]["status"] == "failed"


def test_upload_rejects_missing_manifest(client, auth_headers):
    zip_bytes = build_zip({"call_001.wav": b"fake-audio"})
    resp = client.post(
        "/batches",
        headers=auth_headers,
        files={"file": ("archive.zip", zip_bytes, "application/zip")},
    )
    assert resp.status_code == 400
    assert "manifest" in resp.json()["detail"].lower()


def test_upload_rejects_when_no_audio_matches_manifest(client, auth_headers):
    zip_bytes = build_zip({"manifest.csv": b"name,result_json\nghost.wav,\n"})
    resp = client.post(
        "/batches",
        headers=auth_headers,
        files={"file": ("archive.zip", zip_bytes, "application/zip")},
    )
    assert resp.status_code == 400
    assert "No audio files matched" in resp.json()["detail"]["message"]


def test_upload_succeeds_and_creates_batch(client, auth_headers, monkeypatch):
    _mock_process_batch(monkeypatch)

    resp = client.post(
        "/batches?name=my-batch",
        headers=auth_headers,
        files={"file": ("archive.zip", valid_batch_zip(), "application/zip")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "my-batch"
    assert body["status"] == "pending"
    assert body["total_files"] == 1


def test_get_and_delete_batch(client, auth_headers, monkeypatch):
    _mock_process_batch(monkeypatch)

    created = client.post(
        "/batches",
        headers=auth_headers,
        files={"file": ("archive.zip", valid_batch_zip(), "application/zip")},
    ).json()
    batch_id = created["id"]

    resp = client.get(f"/batches/{batch_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == batch_id

    resp = client.delete(f"/batches/{batch_id}", headers=auth_headers)
    assert resp.status_code == 204

    resp = client.get(f"/batches/{batch_id}", headers=auth_headers)
    assert resp.status_code == 404


def test_get_nonexistent_batch_returns_404(client, auth_headers):
    resp = client.get("/batches/does-not-exist", headers=auth_headers)
    assert resp.status_code == 404


def test_users_cannot_see_or_touch_each_others_batches(client, auth_headers):
    db = SessionLocal()
    try:
        other_user = User(email="other@example.com", hashed_password=hash_password("whatever"))
        db.add(other_user)
        db.commit()
        db.refresh(other_user)

        other_batch = Batch(name="not-yours", owner_id=other_user.id, status="completed")
        db.add(other_batch)
        db.commit()
        db.refresh(other_batch)
        other_batch_id = other_batch.id
    finally:
        db.close()

    resp = client.get("/batches", headers=auth_headers)
    assert other_batch_id not in {b["id"] for b in resp.json()}

    resp = client.get(f"/batches/{other_batch_id}", headers=auth_headers)
    assert resp.status_code == 404

    resp = client.delete(f"/batches/{other_batch_id}", headers=auth_headers)
    assert resp.status_code == 404


def test_download_results_csv(client, auth_headers, monkeypatch):
    _mock_process_batch(monkeypatch)

    created = client.post(
        "/batches",
        headers=auth_headers,
        files={"file": ("archive.zip", valid_batch_zip(), "application/zip")},
    ).json()

    resp = client.get(f"/batches/{created['id']}/download?format=csv", headers=auth_headers)
    assert resp.status_code == 200
    assert "call_001.wav" in resp.text


def test_download_results_json(client, auth_headers, monkeypatch):
    _mock_process_batch(monkeypatch)

    created = client.post(
        "/batches",
        headers=auth_headers,
        files={"file": ("archive.zip", valid_batch_zip(), "application/zip")},
    ).json()

    resp = client.get(f"/batches/{created['id']}/download?format=json", headers=auth_headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload[0]["name"] == "call_001.wav"
