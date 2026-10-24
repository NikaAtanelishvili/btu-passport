"""Students (BE-35): list, register, view, edit, and the program list. Both admin roles."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select, true
from sqlalchemy.orm import Session

from app.auth.deps import AdminUser
from app.db import get_db
from app.models import Passport, PassportVersion, Student
from app.schemas.common import Page
from app.schemas.student import StudentCreate, StudentDetail, StudentPatch, StudentRow
from app.services import students

router = APIRouter(tags=["admin: students"])
DB = Annotated[Session, Depends(get_db)]


@router.get("/students", response_model=Page[StudentRow])
def list_students(
    db: DB,
    q: str | None = None,
    program: str | None = None,
    education_level: str | None = None,
    status: str | None = None,
    has_passport: Annotated[
        bool | None, Query(description="True: a passport has been issued (first_issued_on set)")
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[StudentRow]:
    latest = (
        select(PassportVersion.version_no, PassportVersion.status)
        .where(PassportVersion.passport_id == Passport.passport_id)
        .order_by(PassportVersion.version_no.desc())
        .limit(1)
        .lateral()
    )
    stmt = (
        select(Student, Passport.passport_id, latest.c.version_no, latest.c.status)
        .outerjoin(Passport, Passport.student_id == Student.student_id)
        .outerjoin(latest, true())
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
    if education_level:
        stmt = stmt.where(Student.education_level == education_level)
    if status:
        stmt = stmt.where(Student.status == status)
    if has_passport is not None:
        issued = Passport.first_issued_on.is_not(None)
        stmt = stmt.where(issued if has_passport else ~issued)
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
            latest_version_no=version_no,
            latest_status=version_status,
        )
        for s, passport_id, version_no, version_status in rows
    ]
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.post("/students", status_code=201, response_model=StudentDetail)
def create_student(body: StudentCreate, principal: AdminUser, db: DB) -> StudentDetail:
    """Registers the student with the next Passport ID. 409 duplicate_student_id /
    duplicate_email, with the message under the field."""
    student = students.create_student(db, principal, body)
    return students.detail(db, student.student_id)


@router.get("/students/{student_id}", response_model=StudentDetail)
def get_student(student_id: str, db: DB) -> StudentDetail:
    return students.detail(db, student_id)


@router.patch("/students/{student_id}", response_model=StudentDetail)
def update_student(
    student_id: str, body: StudentPatch, principal: AdminUser, db: DB
) -> StudentDetail:
    """`warnings: ["printed_name_differs"]` when the name no longer matches the issued
    passport; the passport itself is untouched (FR-11)."""
    _, warnings = students.update_student(db, principal, student_id, body)
    return students.detail(db, student_id, warnings)


@router.get("/programs", response_model=list[str])
def list_programs(db: DB) -> list[str]:
    """Distinct programs in students, for the register form's select."""
    return list(db.scalars(select(Student.program).distinct().order_by(Student.program)))
