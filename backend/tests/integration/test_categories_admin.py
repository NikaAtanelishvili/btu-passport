"""BE-51: categories and stamps (FR-07, FR-34, FR-35). Super admin only; admins read. A stamp is
stored by its SHA-256 and never overwritten, so issued PDFs keep the stamp they printed."""

import hashlib
import io
from collections.abc import Callable

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AuditLog, PassportVersion, Skill, SkillCategory
from app.services import issuance, storage
from tests import factories as f
from tests.conftest import FakeChain

ClientAs = Callable[[str | None], TestClient]
RunJobs = Callable[[], int]


@pytest.fixture
def sa(client_as: ClientAs) -> TestClient:
    return client_as("super_admin")


def _png(width: int = 600, height: int = 600, color: str = "navy") -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), color).save(out, "PNG")
    return out.getvalue()


SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
    b'<circle cx="5" cy="5" r="4"/></svg>'
)


def _upload(
    client: TestClient, category_id: int, data: bytes, name: str, mime: str
) -> httpx.Response:
    response: httpx.Response = client.post(
        f"/api/admin/categories/{category_id}/stamp", files={"file": (name, data, mime)}
    )
    return response


def _audit(db: Session, action: str) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id)))


def _new(client: TestClient, name: str) -> int:
    r = client.post("/api/admin/categories", json={"name": name})
    assert r.status_code == 201, r.text
    category_id: int = r.json()["category_id"]
    return category_id


def test_create_numbers_the_next_badge_code(db: Session, sa: TestClient) -> None:
    r = sa.post("/api/admin/categories", json={"name": "AI Research Skill"})
    assert r.status_code == 201, r.text
    assert r.json() | {"category_id": 0} == {
        "category_id": 0,
        "name": "AI Research Skill",
        "badge_code": "BDG-AI-001",
        "stamp_sha256": None,
        "skill_count": 0,
        "archived": False,
    }
    assert sa.post("/api/admin/categories", json={"name": "Second"}).json()["badge_code"] == (
        "BDG-AI-002"
    )
    (entry, _) = _audit(db, "category.create")
    assert entry.actor_email == "superadmin@btu.test"
    assert entry.after == {"name": "AI Research Skill", "badge_code": "BDG-AI-001"}


def test_name_rules(db: Session, sa: TestClient) -> None:
    category_id = _new(sa, "AI Skill")
    blank = sa.post("/api/admin/categories", json={"name": "  "})
    assert blank.status_code == 422 and "name" in blank.json()["fields"]
    dup = sa.post("/api/admin/categories", json={"name": "ai skill"})
    assert (dup.status_code, dup.json()["error"]) == (409, "duplicate_name")
    r = sa.patch(f"/api/admin/categories/{category_id}", json={"name": "AI Core Skill"})
    assert (r.status_code, r.json()["name"]) == (200, "AI Core Skill")
    (entry,) = _audit(db, "category.update")
    assert (entry.before, entry.after) == ({"name": "AI Skill"}, {"name": "AI Core Skill"})
    assert sa.patch("/api/admin/categories/999", json={"name": "x"}).status_code == 404


def test_archived_category_cant_take_new_skills(
    db: Session, client_as: ClientAs, sa: TestClient
) -> None:
    category_id = _new(sa, "AI Skill")
    r = sa.post(f"/api/admin/categories/{category_id}/archive")
    assert (r.status_code, r.json()["archived"]) == (200, True)
    admin = client_as("admin")
    assert admin.get("/api/admin/categories").json() == []
    listed = admin.get("/api/admin/categories", params={"include_archived": True})
    assert [c["archived"] for c in listed.json()] == [True]
    skill = {"name": "New", "category_id": category_id, "description": "d"}
    r = sa.post("/api/admin/skills", json=skill)
    assert r.status_code == 422 and "category_id" in r.json()["fields"]
    assert sa.post(f"/api/admin/categories/{category_id}/unarchive").json()["archived"] is False
    assert sa.post("/api/admin/skills", json=skill).status_code == 201
    assert [len(_audit(db, a)) for a in ("category.archive", "category.unarchive")] == [1, 1]


def test_delete_only_without_skills(db: Session, sa: TestClient) -> None:
    empty = _new(sa, "Empty")
    assert sa.delete(f"/api/admin/categories/{empty}").status_code == 204
    assert db.get(SkillCategory, empty) is None
    assert _audit(db, "category.delete")[0].before == {"name": "Empty", "badge_code": "BDG-AI-001"}
    used = f.skill(db, "SKL-001").category_id
    sk = db.get_one(Skill, "SKL-001")
    sk.archived_at = sk.created_at  # an archived skill still counts
    db.commit()
    r = sa.delete(f"/api/admin/categories/{used}")
    assert (r.status_code, r.json()["error"]) == (409, "in_use")
    assert (
        sa.get("/api/admin/categories", params={"include_archived": True}).json()[0]["skill_count"]
        == 1
    )


def test_png_stamp_is_stored_by_sha256(db: Session, sa: TestClient, s3_bucket: str) -> None:
    category_id = _new(sa, "AI Skill")
    data = _png()
    sha = hashlib.sha256(data).hexdigest()
    r = _upload(sa, category_id, data, "stamp.png", "image/png")
    assert r.status_code == 200, r.text
    assert r.json()["stamp_sha256"] == sha
    row = db.get_one(SkillCategory, category_id)
    db.refresh(row)
    assert (row.stamp_key, row.stamp_mime) == (f"stamps/{sha}.png", "image/png")
    assert storage.get(f"stamps/{sha}.png") == data
    served = sa.get(f"/api/stamps/{sha}")
    assert (served.status_code, served.content, served.headers["content-type"]) == (
        200,
        data,
        "image/png",
    )
    assert "sandbox" in served.headers["content-security-policy"]
    (entry,) = _audit(db, "category.stamp")
    assert (entry.before, entry.after) == ({"stamp_sha256": None}, {"stamp_sha256": sha})
    assert _upload(sa, category_id, data, "again.png", "image/png").status_code == 200
    assert len(_audit(db, "category.stamp")) == 1  # the same image changes nothing


def test_svg_stamp(db: Session, sa: TestClient, s3_bucket: str) -> None:
    category_id = _new(sa, "AI Skill")
    r = _upload(sa, category_id, SVG, "stamp.svg", "image/svg+xml")
    assert r.status_code == 200, r.text
    sha = hashlib.sha256(SVG).hexdigest()
    assert sa.get(f"/api/stamps/{sha}").headers["content-type"] == "image/svg+xml"


@pytest.mark.parametrize(("width", "height"), [(656, 211), (328, 284), (300, 300), (211, 656)])
def test_png_stamps_of_any_shape(sa: TestClient, s3_bucket: str, width: int, height: int) -> None:
    """The designed stamps are a banner, a triangle and a circle: any aspect ratio, longest side
    at least 300 px."""
    category_id = _new(sa, "AI Skill")
    r = _upload(sa, category_id, _png(width, height), "stamp.png", "image/png")
    assert r.status_code == 200, r.text


@pytest.mark.parametrize(
    ("data", "name", "mime", "why"),
    [
        (_png(299, 200), "small.png", "image/png", "300"),
        (_png(120, 299), "tall.png", "image/png", "300"),
        (b"\x89PNG\r\n\x1a\n" + b"junk" * 10, "broken.png", "image/png", "PNG or SVG"),
        (b"GIF89a....", "stamp.gif", "image/gif", "PNG or SVG"),
        (b"x" * (1024 * 1024 + 1), "big.png", "image/png", "1 MB"),
        (
            b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
            "s.svg",
            "image/svg+xml",
            "script",
        ),
        (
            b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>',
            "s.svg",
            "image/svg+xml",
            "script",
        ),
        (
            b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:x="http://www.w3.org/1999/xlink">'
            b'<image x:href="https://evil.example/x.png"/></svg>',
            "s.svg",
            "image/svg+xml",
            "external",
        ),
        (
            b'<!DOCTYPE svg [<!ENTITY a "aaaa">]><svg xmlns="http://www.w3.org/2000/svg">&a;</svg>',
            "s.svg",
            "image/svg+xml",
            "DOCTYPE",
        ),
        (b"<html><body/></html>", "s.svg", "image/svg+xml", "PNG or SVG"),
    ],
    ids=[
        "small",
        "tall-but-short",
        "broken-png",
        "gif",
        "too-big",
        "script",
        "onload",
        "external-href",
        "doctype",
        "not-svg",
    ],
)
def test_bad_stamps_are_refused(
    db: Session, sa: TestClient, s3_bucket: str, data: bytes, name: str, mime: str, why: str
) -> None:
    category_id = _new(sa, "AI Skill")
    r = _upload(sa, category_id, data, name, mime)
    assert r.status_code == 422, r.text
    assert why in r.json()["fields"]["file"]
    assert db.get_one(SkillCategory, category_id).stamp_sha256 is None


def test_replacing_a_stamp_leaves_issued_pdfs_alone(
    db: Session, sa: TestClient, s3_bucket: str, fake_chain: FakeChain, run_jobs: RunJobs
) -> None:
    st, sk = f.student(db, 1), f.skill(db, "SKL-001")
    db.commit()
    old, new = _png(color="navy"), _png(color="darkred")
    old_sha, new_sha = hashlib.sha256(old).hexdigest(), hashlib.sha256(new).hexdigest()
    assert _upload(sa, sk.category_id, old, "a.png", "image/png").status_code == 200
    f.award(db, st, sk)
    (v1,) = issuance.create_versions(db, [st.student_id])
    db.commit()
    run_jobs()
    db.expire_all()
    first = db.get_one(PassportVersion, v1.version_id)
    assert first.status == "ANCHORED" and first.content_json is not None
    assert first.content_json["skills"][0]["stamp_sha256"] == old_sha
    pdf_before = storage.get(first.pdf_key or "")

    assert _upload(sa, sk.category_id, new, "b.png", "image/png").status_code == 200
    db.expire_all()
    first = db.get_one(PassportVersion, v1.version_id)
    assert first.content_json is not None
    assert first.content_json["skills"][0]["stamp_sha256"] == old_sha
    assert storage.get(first.pdf_key or "") == pdf_before
    assert hashlib.sha256(pdf_before).hexdigest() == first.pdf_sha256
    assert sa.get(f"/api/stamps/{old_sha}").content == old  # still served for old pages
    assert sa.get(f"/api/verify/{first.verification_code}").json()["verdict"] == "VALID"

    f.award(db, st, f.skill(db, "SKL-002"))
    db.execute(update(Skill).where(Skill.skill_id == "SKL-002").values(category_id=sk.category_id))
    (v2,) = issuance.create_versions(db, [st.student_id])
    db.commit()
    run_jobs()
    db.expire_all()
    second = db.get_one(PassportVersion, v2.version_id)
    assert second.content_json is not None
    assert {s["stamp_sha256"] for s in second.content_json["skills"]} == {new_sha}


def test_db_keeps_stamps_keyed_by_sha256(db: Session) -> None:
    category = db.get_one(SkillCategory, f.skill(db, "SKL-001").category_id)
    category.stamp_sha256, category.stamp_mime = "ab" * 32, "image/png"
    category.stamp_key = "stamps/other.png"
    with pytest.raises(IntegrityError):
        db.flush()
