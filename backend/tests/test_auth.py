from app.config import get_settings

settings = get_settings()


def test_login_succeeds_with_correct_credentials(client):
    resp = client.post(
        "/auth/login",
        json={"email": settings.admin_email, "password": settings.admin_password},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 0


def test_login_rejects_wrong_password(client):
    resp = client.post(
        "/auth/login",
        json={"email": settings.admin_email, "password": "wrong-password"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid email or password"


def test_login_rejects_unknown_email(client):
    resp = client.post(
        "/auth/login",
        json={"email": "nobody@nowhere.com", "password": "whatever"},
    )
    assert resp.status_code == 401


def test_batches_require_authentication(client):
    resp = client.get("/batches")
    assert resp.status_code == 403  # HTTPBearer with no credentials


def test_batches_reject_invalid_token(client):
    resp = client.get("/batches", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


def test_login_is_rate_limited(client):
    # limit is 5/minute (see routes/auth.py) -- the 6th attempt in the same
    # window should be rejected before it even touches the password check.
    for _ in range(5):
        resp = client.post(
            "/auth/login",
            json={"email": settings.admin_email, "password": "wrong-password"},
        )
        assert resp.status_code == 401

    resp = client.post(
        "/auth/login",
        json={"email": settings.admin_email, "password": "wrong-password"},
    )
    assert resp.status_code == 429
