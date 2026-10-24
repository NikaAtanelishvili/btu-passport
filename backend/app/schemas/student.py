"""Student schemas (admin)."""

from pydantic import BaseModel


class StudentRow(BaseModel):
    student_id: str
    first_name: str
    last_name: str
    email: str
    program: str
    education_level: str
    status: str
    passport_id: str | None
