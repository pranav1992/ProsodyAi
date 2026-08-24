from sqlalchemy.orm import Session


def test_unhandled_exception_returns_clean_500(client, auth_headers, monkeypatch):
    def _boom(self, *args, **kwargs):
        raise RuntimeError("simulated unexpected failure")

    monkeypatch.setattr(Session, "query", _boom)

    resp = client.get("/batches", headers=auth_headers)

    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal server error"}


def test_unhandled_exception_response_still_carries_cors_headers(client, auth_headers, monkeypatch):
    # A raw exception handled by Starlette's default ServerErrorMiddleware
    # (instead of an app-registered handler) can skip CORSMiddleware and
    # come back without CORS headers -- which the browser reports as a CORS
    # error, masking the real 500. Our @app.exception_handler(Exception)
    # keeps the response inside the normal middleware stack.
    def _boom(self, *args, **kwargs):
        raise RuntimeError("simulated unexpected failure")

    monkeypatch.setattr(Session, "query", _boom)

    resp = client.get(
        "/batches",
        headers={**auth_headers, "Origin": "http://localhost:3000"},
    )

    assert resp.status_code == 500
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
