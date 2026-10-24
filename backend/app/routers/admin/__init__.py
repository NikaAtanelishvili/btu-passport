"""Admin API (/api/admin/*). Every route needs ADMIN or SUPER_ADMIN (BE-12)."""

from fastapi import APIRouter, Depends

from app.auth.deps import require_admin
from app.routers.admin import awards, students

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])
router.include_router(students.router)
router.include_router(awards.router)
