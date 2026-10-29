from fastapi.testclient import TestClient
from backend.app.config import allowed_origins
from backend.app.main import app


def test_frontend_origins_are_explicit_and_normalized(monkeypatch):
    monkeypatch.setenv("ARGUS_ALLOWED_ORIGINS", " https://argus.example/ ,https://preview.example ")
    assert allowed_origins() == ["https://argus.example", "https://preview.example"]


def test_local_investigation_patch_preflight_is_supported():
    with TestClient(app) as client:
        response = client.options("/api/incidents/test/investigation", headers={
            "Origin": "http://127.0.0.1:5173", "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "content-type",
        })
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
