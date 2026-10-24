"""BE-13: double-submit CSRF for state-changing requests under /api/ and /auth/logout."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import SignedIn
from app.models import UserSession

ClientAs = Callable[[str | None], TestClient]


@pytest.fixture
def client(client_as: ClientAs) -> TestClient:
    c = client_as("admin")
    app = c.app

    @app.post("/api/_test/change")  # type: ignore[attr-defined, untyped-decorator]
    def change(p: SignedIn) -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/verify/_test")  # type: ignore[attr-defined, untyped-decorator]
    def public_post() -> dict[str, bool]:
        return {"ok": True}

    return c


def _without_header(client: TestClient) -> TestClient:
    client.headers.pop("X-CSRF-Token", None)
    return client


def test_post_without_header_is_rejected(client: TestClient) -> None:
    response = _without_header(client).post("/api/_test/change")
    assert response.status_code == 403
    assert response.json()["error"] == "csrf_failed"


def test_post_with_wrong_header_is_rejected(client: TestClient) -> None:
    response = client.post("/api/_test/change", headers={"X-CSRF-Token": "wrong"})
    assert response.status_code == 403


def test_post_with_matching_header_passes(client: TestClient) -> None:
    assert client.post("/api/_test/change").status_code == 200


def test_get_needs_no_header(client: TestClient) -> None:
    assert _without_header(client).get("/api/admin/students").status_code == 200


def test_logout_needs_the_header(client: TestClient, db: Session) -> None:
    csrf = client.headers["X-CSRF-Token"]
    assert _without_header(client).post("/auth/logout").status_code == 403
    assert db.scalar(select(func.count()).select_from(UserSession)) == 1
    assert client.post("/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert db.scalar(select(func.count()).select_from(UserSession)) == 0


def test_public_verify_is_exempt(client: TestClient) -> None:
    assert _without_header(client).post("/api/verify/_test").status_code == 200


def test_no_session_falls_through_to_the_guard(client_as: ClientAs) -> None:
    c = client_as(None)
    app = c.app

    @app.post("/api/_test/change")  # type: ignore[attr-defined, untyped-decorator]
    def change(p: SignedIn) -> dict[str, bool]:
        return {"ok": True}

    assert c.post("/api/_test/change").status_code == 401
