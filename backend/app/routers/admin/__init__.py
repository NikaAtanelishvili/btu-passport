"""Admin API (/api/admin/*). Every route needs ADMIN or SUPER_ADMIN (BE-12)."""

from fastapi import APIRouter, Depends

from app.auth.deps import require_admin
from app.routers.admin import (
    awards,
    categories,
    dashboard,
    events,
    skills,
    students,
    versions,
)

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])
router.include_router(dashboard.router)
router.include_router(students.router)
router.include_router(skills.router)
router.include_router(categories.router)
router.include_router(awards.router)
router.include_router(versions.router)
router.include_router(events.router)
