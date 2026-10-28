"""Sheet sync runs for the worker and the admin API (SH-05): enqueue (manual or scheduled),
the worker's job, status and listings."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import case, func, or_, select, text
from sqlalchemy.orm import Session, aliased

from app.config import get_settings
from app.db import SessionLocal
from app.models import (
    Passport,
    PassportVersion,
    SheetRecord,
    SheetSyncRun,
    SkillAward,
    Student,
)
from app.schemas.common import Page
from app.schemas.sheets import SheetRecordRow, SheetRunOut, SheetStatus, SyncRequested
from app.services import audit, jobs
from app.sheets import sync, writeback
from app.sheets.source import GoogleSheetSource, SheetSource, SourceError

if TYPE_CHECKING:
    from app.auth.deps import Principal

DEDUPE_KEY = "sheet-sync"
FLAG_OUTCOMES = ("CHANGED_AFTER_PROCESSING", "REVOKED_IN_SHEET", "CONFLICT")
ATTENTION = ("ERROR", *FLAG_OUTCOMES)


def configured() -> bool:
    return bool(get_settings().google_sheets_id)


def enqueue(db: Session, trigger: str, actor: "Principal | None" = None) -> SyncRequested:
    """A QUEUED run and its SHEET_SYNC job, or the run already queued or running. The advisory
    lock makes two concurrent requests agree on one run."""
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": DEDUPE_KEY})
    if (active := sync.active_run(db)) is not None:
        return SyncRequested(run_id=active.run_id, status=active.status, already_running=True)
    run_id = sync.create_run(db, trigger, GoogleSheetSource.label)
    # One attempt: a failed run is FAILED and the next interval tries again.
    jobs.enqueue(db, "SHEET_SYNC", {"run_id": run_id}, dedupe_key=DEDUPE_KEY, max_attempts=1)
    if actor is not None:
        audit.record(db, actor, "sheet.sync.request", "sheet_sync_run", str(run_id))
    return SyncRequested(run_id=run_id, status="QUEUED", already_running=False)


def _last_scheduled_base(db: Session) -> datetime | None:
    """When the schedule counts from: the newest run that read the Sheet (not an upload)."""
    return db.scalar(
        select(func.max(SheetSyncRun.created_at)).where(SheetSyncRun.trigger != "UPLOAD")
    )


def next_run_at(db: Session) -> datetime | None:
    if not configured():
        return None
    last = _last_scheduled_base(db)
    interval = timedelta(seconds=get_settings().sheet_sync_interval_seconds)
    return last + interval if last else datetime.now(UTC)


def tick(db: Session) -> int | None:
    """Worker timer: enqueue a SCHEDULE run when the interval has passed since the last run.
    Returns the new run's ID. Disabled without GOOGLE_SHEETS_ID."""
    if not configured():
        return None
    due = next_run_at(db)
    if due is not None and due > datetime.now(UTC):
        return None
    requested = enqueue(db, "SCHEDULE")
    return None if requested.already_running else requested.run_id


def source_for_run() -> SheetSource:
    """The Sheet the worker reads (tests replace this)."""
    return GoogleSheetSource()


def run_job(run_id: int) -> sync.SyncResult:
    """The SHEET_SYNC job: read, decide, process (SH-04), then write back (SH-06)."""
    try:
        source = source_for_run()
    except SourceError as exc:
        return sync.fail_run(run_id, str(exc))
    result = sync.execute(run_id, source)
    if isinstance(source, writeback.WritableSource):
        writeback.write_back(result, source)
    return result


def give_up(run_id: int, error: str) -> None:
    with SessionLocal() as db, db.begin():
        run = db.get(SheetSyncRun, run_id, with_for_update=True)
        if run is not None and run.status in ("QUEUED", "RUNNING"):
            run.status = "FAILED"
            run.error = f"The sync job failed: {error}"[:500]
            run.finished_at = datetime.now(UTC)


def run_out(run: SheetSyncRun) -> SheetRunOut:
    return SheetRunOut.model_validate(run, from_attributes=True)


def status(db: Session) -> SheetStatus:
    s = get_settings()
    last = db.scalars(
        select(SheetSyncRun).order_by(SheetSyncRun.run_id.desc()).limit(1)
    ).one_or_none()
    active = sync.active_run(db)
    counts = dict(
        db.execute(
            select(SheetRecord.outcome, func.count())
            .where(SheetRecord.outcome.in_(ATTENTION))
            .group_by(SheetRecord.outcome)
        ).all()
    )
    return SheetStatus(
        configured=configured(),
        writeback=s.sheet_writeback,
        interval_seconds=s.sheet_sync_interval_seconds,
        last_run=run_out(last) if last else None,
        last_success_at=db.scalar(
            select(func.max(SheetSyncRun.finished_at)).where(SheetSyncRun.status == "DONE")
        ),
        next_run_at=next_run_at(db),
        active_run_id=active.run_id if active else None,
        errors=counts.get("ERROR", 0),
        flags=sum(counts.get(o, 0) for o in FLAG_OUTCOMES),
    )


def list_runs(db: Session, page: int, page_size: int) -> Page[SheetRunOut]:
    total = db.scalar(select(func.count()).select_from(SheetSyncRun)) or 0
    runs = db.scalars(
        select(SheetSyncRun)
        .order_by(SheetSyncRun.run_id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Page(items=[run_out(r) for r in runs], total=total, page=page, page_size=page_size)


def list_records(
    db: Session,
    *,
    outcome: str | None,
    tab: str | None,
    q: str | None,
    page: int,
    page_size: int,
) -> Page[SheetRecordRow]:
    """Errors and flags first, then Verified Skills, Students, Skills Catalog, by row."""
    row_student = aliased(Student)
    student_id = func.coalesce(
        SkillAward.student_id, Passport.student_id, row_student.student_id
    ).label("student_id")
    stmt: Any = (
        select(
            SheetRecord,
            student_id,
            PassportVersion.passport_id,
            PassportVersion.version_no,
        )
        .outerjoin(SkillAward, SkillAward.award_id == SheetRecord.award_id)
        .outerjoin(PassportVersion, PassportVersion.version_id == SheetRecord.version_id)
        .outerjoin(Passport, Passport.passport_id == PassportVersion.passport_id)
        .outerjoin(
            row_student,
            (SheetRecord.tab == "Students") & (row_student.student_id == SheetRecord.key),
        )
    )
    if outcome:
        stmt = stmt.where(SheetRecord.outcome.in_([o.strip().upper() for o in outcome.split(",")]))
    if tab:
        stmt = stmt.where(SheetRecord.tab == tab)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                SheetRecord.key.ilike(like), SheetRecord.message.ilike(like), student_id.ilike(like)
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    tab_order = case(
        {"Verified Skills": 0, "Students": 1, "Skills Catalog": 2}, value=SheetRecord.tab
    )
    rows = db.execute(
        stmt.order_by(
            case((SheetRecord.outcome.in_(ATTENTION), 0), else_=1),
            tab_order,
            SheetRecord.row_number,
            SheetRecord.key,
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page(
        items=[
            SheetRecordRow(
                tab=r.tab,
                key=r.key,
                row_number=r.row_number,
                outcome=r.outcome,
                message=r.message,
                first_seen_at=r.first_seen_at,
                decided_at=r.decided_at,
                student_id=sid,
                passport_id=passport_id,
                version_id=r.version_id,
                version_no=version_no,
            )
            for r, sid, passport_id, version_no in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
