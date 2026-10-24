"""BE-14: GET /api/session for each kind of caller."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

ClientAs = Callable[[str | None], TestClient]


def test_signed_out(client_as: ClientAs) -> None:
    response = client_as(None).get("/api/session")
    assert (response.status_code, response.json()) == (200, {"authenticated": False})


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (
            "super_admin",
            {"authenticated": True, "user": {"email": "superadmin@btu.test", "name": "superadmin"},
             "role": "SUPER_ADMIN", "student": None},
        ),
        (
            "admin",
            {"authenticated": True, "user": {"email": "admin@btu.test", "name": "admin"},
             "role": "ADMIN", "student": None},
        ),
        (
            "student",
            {"authenticated": True,
             "user": {"email": "btu-t-0001@example.org", "name": "btu-t-0001"},
             "role": None, "student": {"student_id": "BTU-T-0001", "passport_id": "BTU-AI-000001"}},
        ),
        (
            "unregistered",
            {"authenticated": True, "user": {"email": "newcomer@btu.test", "name": "newcomer"},
             "role": None, "student": None},
        ),
    ],
)  # fmt: skip
def test_signed_in(client_as: ClientAs, role: str, expected: dict[str, object]) -> None:
    response = client_as(role).get("/api/session")
    assert (response.status_code, response.json()) == (200, expected)
