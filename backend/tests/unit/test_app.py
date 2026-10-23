from fastapi import Query
from fastapi.testclient import TestClient

from app.errors import AppError
from app.main import create_app


def _client() -> TestClient:
    app = create_app()

    @app.get("/api/_test/app-error")
    def app_error() -> None:
        raise AppError("duplicate_email", "Email already registered.", 409, {"email": "taken"})

    @app.get("/api/_test/validation")
    def validation(page: int = Query(ge=1)) -> dict[str, int]:
        return {"page": page}

    return TestClient(app)


def test_healthz() -> None:
    response = _client().get("/api/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_app_error_shape() -> None:
    response = _client().get("/api/_test/app-error")
    assert response.status_code == 409
    assert response.json() == {
        "error": "duplicate_email",
        "message": "Email already registered.",
        "fields": {"email": "taken"},
    }


def test_validation_error_is_422_keyed_by_field() -> None:
    response = _client().get("/api/_test/validation?page=0")
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "validation_error"
    assert set(body["fields"]) == {"page"}


def test_unknown_route_uses_error_shape() -> None:
    response = _client().get("/api/nope")
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"
