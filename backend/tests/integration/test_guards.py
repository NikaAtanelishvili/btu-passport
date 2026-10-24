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
