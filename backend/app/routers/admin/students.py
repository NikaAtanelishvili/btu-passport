"""Students (BE-35). M3 ships the read-only list so the admin guard has a real route (A11)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Passport, Student
from app.schemas.common import Page
from app.schemas.student import StudentRow

router = APIRouter(tags=["admin: students"])


@router.get("/students", response_model=Page[StudentRow])
def list_students(
    db: Annotated[Session, Depends(get_db)],
    q: str | None = None,
    program: str | None = None,
    status: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[StudentRow]:
    stmt = select(Student, Passport.passport_id).outerjoin(
        Passport, Passport.student_id == Student.student_id
    )
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Student.student_id.ilike(like),
                Student.email.ilike(like),
                (Student.first_name + " " + Student.last_name).ilike(like),
            )
        )
    if program:
        stmt = stmt.where(Student.program == program)
    if status:
        stmt = stmt.where(Student.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(Student.student_id).offset((page - 1) * page_size).limit(page_size)
    ).all()
    items = [
        StudentRow(
            student_id=s.student_id,
            first_name=s.first_name,
            last_name=s.last_name,
            email=s.email,
            program=s.program,
            education_level=s.education_level,
            status=s.status,
            passport_id=passport_id,
        )
        for s, passport_id in rows
    ]
    return Page(items=items, total=total, page=page, page_size=page_size)
