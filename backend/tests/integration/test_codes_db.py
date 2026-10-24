"""BE-20: IDs drawn from the database."""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import SkillCategory
from app.services import codes
from tests import factories as f


def test_next_passport_id_uses_the_sequence(db: Session) -> None:
    db.execute(text("SELECT setval('passport_number_seq', 142)"))
    assert codes.next_passport_id(db) == "BTU-AI-000143"
    assert codes.next_passport_id(db) == "BTU-AI-000144"


def test_next_skill_id_and_badge_code(db: Session) -> None:
    assert codes.next_skill_id(db) == "SKL-001"
    assert codes.next_badge_code(db) == "BDG-AI-001"
    f.skill(db, "SKL-016")
    db.add(SkillCategory(name="AI Research Skill", badge_code="BDG-AI-003"))
    db.flush()
    assert codes.next_skill_id(db) == "SKL-017"
    assert codes.next_badge_code(db) == "BDG-AI-004"
