"""CSRF / cross-origin containment for the loopback API.

A drive-by web page must not be able to drive state-changing endpoints on the
local backend. The guard rejects any unsafe-method request carrying a foreign
``Origin`` header before it reaches a handler, while leaving same-origin app
traffic, the Tauri webview, and non-browser callers (no Origin) untouched.

The tests exercise the middleware in isolation by POSTing to ``/api/health`` (a
GET-only route): the guard runs before routing, so an allowed origin falls
through to 405 (proving it passed) and a foreign origin is refused with 403.
"""
from fastapi.testclient import TestClient

from hydra.app import create_app

CSRF_DETAIL = "Cross-origin state-changing request refused"


def _client() -> TestClient:
    return TestClient(create_app())


def test_foreign_origin_state_change_is_refused():
    with _client() as client:
        response = client.post("/api/health", headers={"origin": "https://evil.example"})
    assert response.status_code == 403
    assert response.json()["detail"] == CSRF_DETAIL


def test_allowed_frontend_origin_passes_guard():
    with _client() as client:
        response = client.post("/api/health", headers={"origin": "http://127.0.0.1:5173"})
    # Guard passed; the GET-only route rejects the method afterwards.
    assert response.status_code == 405


def test_tauri_production_origin_passes_guard():
    with _client() as client:
        response = client.post("/api/health", headers={"origin": "tauri://localhost"})
    assert response.status_code == 405


def test_missing_origin_passes_guard():
    # Non-browser callers (curl, Tauri IPC, tests) send no Origin and must work.
    with _client() as client:
        response = client.post("/api/health")
    assert response.status_code == 405


def test_safe_method_from_foreign_origin_is_allowed():
    with _client() as client:
        response = client.get("/api/health", headers={"origin": "https://evil.example"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_delete_from_foreign_origin_is_refused():
    with _client() as client:
        response = client.delete("/api/health", headers={"origin": "https://evil.example"})
    assert response.status_code == 403


def test_foreign_origin_blocked_on_real_state_changing_endpoint():
    # A genuine mutation route (not just the health probe) is protected too.
    with _client() as client:
        response = client.post(
            "/api/console/run",
            headers={"origin": "https://evil.example"},
            json={"command": "echo pwned"},
        )
    assert response.status_code == 403
    assert response.json()["detail"] == CSRF_DETAIL
