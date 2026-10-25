"""BE-12: guards. Roles are read from user_roles on every request (A11, A12 session part)."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.auth.deps import SignedIn, StudentUser, SuperAdminUser
from app.models import UserRole

ClientAs = Callable[[str | None], TestClient]


@pytest.fixture
def guarded(client_as: ClientAs) -> Callable[[str | None], TestClient]:
    """client_as plus test-only routes behind each guard."""

    def make(role: str | None) -> TestClient:
        client = client_as(role)
        app = client.app

        @app.get("/api/_test/user")  # type: ignore[attr-defined, untyped-decorator]
        def user(p: SignedIn) -> dict[str, str | None]:
            return {"email": p.user.email, "role": p.role}

        @app.get("/api/_test/student")  # type: ignore[attr-defined, untyped-decorator]
        def student(p: StudentUser) -> dict[str, str]:
            assert p.student is not None
            return {"student_id": p.student.student_id}

        @app.get("/api/_test/super")  # type: ignore[attr-defined, untyped-decorator]
        def super_(p: SuperAdminUser) -> dict[str, str]:
            return {"ok": "yes"}

        return client

    return make


@pytest.mark.parametrize(
    ("role", "user", "student", "super_"),
    [
        (None, 401, 401, 401),
        ("unregistered", 200, 403, 403),
        ("student", 200, 200, 403),
        ("admin", 200, 403, 403),
        ("super_admin", 200, 403, 200),
    ],
)
def test_guard_matrix(
    guarded: Callable[[str | None], TestClient],
    role: str | None,
    user: int,
    student: int,
    super_: int,
) -> None:
    client = guarded(role)
    assert client.get("/api/_test/user").status_code == user
    assert client.get("/api/_test/student").status_code == student
    assert client.get("/api/_test/super").status_code == super_


def test_error_codes(guarded: Callable[[str | None], TestClient]) -> None:
    assert guarded(None).get("/api/_test/user").json()["error"] == "unauthenticated"
    admin = guarded("admin")
    assert admin.get("/api/_test/student").json()["error"] == "not_a_student"
    assert admin.get("/api/_test/super").json()["error"] == "forbidden"


def test_A11_student_forbidden(client_as: ClientAs) -> None:
    response = client_as("student").get("/api/admin/students")
    assert response.status_code == 403
    assert response.json()["error"] == "forbidden"
    assert client_as(None).get("/api/admin/students").status_code == 401


def test_admin_can_list_students(client_as: ClientAs) -> None:
    for role in ("admin", "super_admin"):
        response = client_as(role).get("/api/admin/students")
        assert response.status_code == 200
        assert set(response.json()) == {"items", "total", "page", "page_size"}


def test_A12_revoked_admin_next_request_forbidden(client_as: ClientAs, db: Session) -> None:
    client = client_as("admin")
    assert client.get("/api/admin/students").status_code == 200
    db.execute(delete(UserRole).where(UserRole.email == "admin@btu.test"))
    db.commit()
    assert client.get("/api/admin/students").status_code == 403


def test_promoted_user_gets_access_without_signing_in_again(
    client_as: ClientAs, db: Session
) -> None:
    client = client_as("unregistered")
    assert client.get("/api/admin/students").status_code == 403
    db.add(UserRole(email="newcomer@btu.test", role="ADMIN"))
    db.commit()
    assert client.get("/api/admin/students").status_code == 200


def _admin_routes() -> list[tuple[str, str]]:
    """Every (method, path) under /api/admin/, from the OpenAPI schema (included routers
    aren't expanded in app.routes)."""
    from app.main import create_app

    paths = create_app().openapi()["paths"]
    return sorted(
        (method.upper(), path)
        for path, ops in paths.items()
        if path.startswith("/api/admin/")
        for method in ops
    )


def test_admin_routes_exist() -> None:
    paths = {path for _, path in _admin_routes()}
    assert {
        "/api/admin/dashboard",
        "/api/admin/students",
        "/api/admin/students/{student_id}",
        "/api/admin/programs",
        "/api/admin/skills",
        "/api/admin/awards",
        "/api/admin/awards/preview",
        "/api/admin/versions",
        "/api/admin/versions/{version_id}/retry",
        "/api/admin/versions/retry-failed",
        "/api/admin/versions/{version_id}/pdf",
        "/api/admin/events",
        "/api/admin/events/{event_id}",
        "/api/admin/events/{event_id}/open",
        "/api/admin/events/{event_id}/close",
        "/api/admin/events/{event_id}/reopen",
        "/api/admin/events/{event_id}/complete",
        "/api/admin/events/{event_id}/participants",
        "/api/admin/events/{event_id}/participants/{email}",
        "/api/admin/events/{event_id}/qr",
    } <= paths


@pytest.mark.parametrize(("method", "path"), _admin_routes())
def test_A11_student_forbidden_on_every_admin_route(
    client_as: ClientAs, method: str, path: str
) -> None:
    """Every /api/admin/* route, with any path parameters filled in, refuses a student before
    looking at the request (403, not 404 or 422)."""
    url = (
        path.replace("{student_id}", "BTU-T-0001")
        .replace("{version_id}", "1")
        .replace("{event_id}", "6b1f5d1e-6a43-4e0e-9d6c-2f1f5c3b9a10")
        .replace("{email}", "btu-t-0001@example.org")
        .replace("{skill_id}", "SKL-001")
        .replace("{category_id}", "1")
    )
    response = client_as("student").request(method, url, json={})
    assert response.status_code == 403, response.text
    assert response.json()["error"] == "forbidden"


def _super_admin_only(method: str, path: str) -> bool:
    """Writes to events and the catalog, the presenter QR, and all of roles and audit; admins
    read events, skills and categories (Frontend tab §1, Backend tab §5)."""
    if path.startswith(("/api/admin/roles", "/api/admin/audit")):
        return True
    if path.endswith("/qr"):
        return True
    catalog = path.startswith(("/api/admin/events", "/api/admin/skills", "/api/admin/categories"))
    return catalog and method != "GET"


SUPER_ADMIN_ROUTES = [r for r in _admin_routes() if _super_admin_only(*r)]


def test_super_admin_routes_exist() -> None:
    assert {
        ("POST", "/api/admin/skills"),
        ("PATCH", "/api/admin/skills/{skill_id}"),
        ("DELETE", "/api/admin/skills/{skill_id}"),
        ("POST", "/api/admin/skills/{skill_id}/archive"),
        ("POST", "/api/admin/skills/{skill_id}/unarchive"),
        ("POST", "/api/admin/categories"),
        ("PATCH", "/api/admin/categories/{category_id}"),
        ("DELETE", "/api/admin/categories/{category_id}"),
        ("POST", "/api/admin/categories/{category_id}/archive"),
        ("POST", "/api/admin/categories/{category_id}/unarchive"),
        ("POST", "/api/admin/categories/{category_id}/stamp"),
        ("GET", "/api/admin/roles"),
        ("PUT", "/api/admin/roles/{email}"),
        ("DELETE", "/api/admin/roles/{email}"),
        ("GET", "/api/admin/audit"),
        ("GET", "/api/admin/audit/actions"),
    } <= set(SUPER_ADMIN_ROUTES)


@pytest.mark.parametrize(("method", "path"), SUPER_ADMIN_ROUTES)
def test_admin_forbidden_on_every_super_admin_route(
    client_as: ClientAs, method: str, path: str
) -> None:
    """An Admin (not super admin) gets 403 before anything is looked up or changed."""
    url = (
        path.replace("{event_id}", "6b1f5d1e-6a43-4e0e-9d6c-2f1f5c3b9a10")
        .replace("{email}", "superadmin@btu.test")
        .replace("{skill_id}", "SKL-001")
        .replace("{category_id}", "1")
    )
    response = client_as("admin").request(method, url, json={})
    assert response.status_code == 403, response.text
    assert response.json()["error"] == "forbidden"
