"""Verification codes and generated IDs (BE-20)."""

import re
import secrets

from sqlalchemy import select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.models import Skill, SkillCategory, passport_number_seq

# Crockford base32: no I, L, O, U, so codes are easy to read and type.
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
CODE_LENGTH = 10  # 50 bits
_LOOK_ALIKES = str.maketrans({"O": "0", "I": "1", "L": "1"})


def new_verification_code() -> str:
    """Random, never derived from the PDF hash. Uniqueness is checked by the caller."""
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def format_code(code: str) -> str:
    """'K7QM3XWP9D' -> 'K7QM-3XWP-9D' (how it is printed and shown)."""
    return f"{code[:4]}-{code[4:8]}-{code[8:]}"


def normalize_code(text: str) -> str:
    """Accept any case, dashes and spaces, and the look-alikes O, I, L. Raise on anything else."""
    code = re.sub(r"[\s-]", "", text).upper().translate(_LOOK_ALIKES)
    if not code or any(c not in ALPHABET for c in code):
        raise ValueError("not a verification code")
    return code


def next_passport_id(db: Session) -> str:
    return f"BTU-AI-{db.scalar(passport_number_seq.next_value()):06d}"


def _next_number(db: Session, column: InstrumentedAttribute[str], prefix: str) -> str:
    """Highest existing '<prefix>nnn' + 1, zero-padded to 3."""
    numbers = db.scalars(select(column).where(column.like(f"{prefix}%")))
    highest = max((int(v[len(prefix) :]) for v in numbers if v[len(prefix) :].isdigit()), default=0)
    return f"{prefix}{highest + 1:03d}"


def next_skill_id(db: Session) -> str:
    return _next_number(db, Skill.skill_id, "SKL-")


def next_badge_code(db: Session) -> str:
    return _next_number(db, SkillCategory.badge_code, "BDG-AI-")
