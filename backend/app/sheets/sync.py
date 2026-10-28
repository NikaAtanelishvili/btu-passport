"""The Sheet sync engine (SH-04): one run reads the three tabs, decides an outcome for every row
and hands new CONFIRMED records to the issuance pipeline (docs/plan/05-addendum-sheets.md §5).

Order: Skills Catalog, then Students, then Verified Skills, each in its own transaction(s):
- Skills and students are applied row by row in savepoints, so one bad row changes nothing
  else. A Sheet row is applied only when it is new or changed since its last decision, so an
  admin's later edit in the panel isn't overwritten by an unchanged row on every run.
- Verified Skills: all decisions are made in memory against one snapshot; then each student
  with new records gets one transaction holding one SHEET submission, the awards and one new
  version (D8). One student's failure never touches another's.
- Processed records are immutable (D6, D7): an edit or a REJECTED status is flagged, never
  applied. `skill_awards.source_record_id UNIQUE` makes a second award for a record
  impossible, whatever happens concurrently.
"""

import hashlib
import json
import logging
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.errors import AppError
from app.models import (
    AwardSubmission,
    Event,
    Passport,
    PassportVersion,
    SheetRecord,
    SheetSyncRun,
    Skill,
    SkillAward,
    SkillCategory,
    Student,
    VersionAward,
)
from app.schemas.student import StudentCreate
from app.services import audit, events, issuance, students
from app.sheets.source import (
    COLUMNS,
    SKILLS,
    STUDENTS,
    TABS,
    VERIFIED,
    Cell,
    Row,
    SheetSource,
    SourceError,
    Tab,
)

log = logging.getLogger("sheets")

RECORD_ID_RE = re.compile(r"^REC-\d{4,}$")
SKILL_CODE_RE = re.compile(r"^SKL-\d{3,}$")
RECORD_STATUSES = ("CONFIRMED", "PENDING", "REJECTED")
EARNED_THROUGH_MAX = 120
SKILL_NAME_MAX = 80
SKILL_DESCRIPTION_MAX = 300
# Google Sheets' serial day 0 (unformatted date cells are days since then).
SHEETS_EPOCH = date(1899, 12, 30)
KEY_COLUMNS = {STUDENTS: "student_id", SKILLS: "skill_code", VERIFIED: "record_id"}
UPPER_COLUMNS = {"student_id", "skill_code", "record_id", "education_level", "status"}
# Outcomes that end a record's processing: an unchanged row with one of them is not re-decided.
FINAL = {
    STUDENTS: ("CREATED", "UPDATED", "UNCHANGED"),
    SKILLS: ("CREATED", "UPDATED", "UNCHANGED"),
    VERIFIED: ("PROCESSED", "DUPLICATE"),
}
FLAGS = ("CHANGED_AFTER_PROCESSING", "REVOKED_IN_SHEET", "CONFLICT")


@dataclass
class Decision:
    tab: str
    key: str
    row: int
    row_hash: str
    outcome: str
    message: str | None = None
    award_id: int | None = None
    version_id: int | None = None
    skipped: bool = False  # unchanged since its last decision (fast path)
    changed_data: bool = False  # created or updated something in the system
    saved: bool = False  # already written to sheet_records in its own transaction


@dataclass
class SyncResult:
    run_id: int
    status: str
    error: str | None = None
    counts: dict[str, dict[str, int]] = field(default_factory=dict)
    decisions: list[Decision] = field(default_factory=list)
    versions: int = 0
    # The Verified Skills tab as read: write-back (SH-06) compares its system cells.
    verified: Tab | None = None


# --- Values ----------------------------------------------------------------------------------


def text_of(value: Cell) -> str:
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def parse_date(value: Cell) -> date | None:
    """A date cell, a Sheets serial number, or text as YYYY-MM-DD or DD.MM.YYYY; None if not."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, int | float) and not isinstance(value, bool):
        return SHEETS_EPOCH + timedelta(days=int(value))
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    return None


def normalise(tab: str, row: Row) -> dict[str, str]:
    """The tab's known columns as trimmed text; keys and codes upper-case, emails lower-case,
    dates as ISO when they parse."""
    required, optional = COLUMNS[tab]
    out = {}
    for column in (*required, *optional):
        raw = row.values.get(column, "")
        value = text_of(raw)
        if column in UPPER_COLUMNS:
            value = value.upper()
        elif column == "email":
            value = value.lower()
        elif column == "date_earned" and value and (parsed := parse_date(raw)) is not None:
            value = parsed.isoformat()
        out[column] = value
    return out


def row_hash(tab: str, values: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps([tab, values], sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class Keyed:
    row: Row
    values: dict[str, str]
    key: str
    first_row: int | None  # the earlier row with the same key, for a repeat


def keyed_rows(tab: Tab) -> list[Keyed]:
    """Rows with their record key. A row without a key is `@<row>`; a repeat of a key already
    seen in the tab is `<key>@<row>`, decided separately and never applied."""
    column = KEY_COLUMNS[tab.name]
    seen: dict[str, int] = {}
    out = []
    for row in tab.rows:
        values = normalise(tab.name, row)
        key = values[column]
        if not key:
            out.append(Keyed(row, values, f"@{row.number}", None))
        elif key in seen:
            out.append(Keyed(row, values, f"{key}@{row.number}", seen[key]))
        else:
            seen[key] = row.number
            out.append(Keyed(row, values, key, None))
    return out


# --- Runs ------------------------------------------------------------------------------------


def create_run(db: Session, trigger: str, source_label: str) -> int:
    """A QUEUED run in the caller's transaction. The partial unique index allows one QUEUED or
    RUNNING run; a second insert raises IntegrityError (SH-05 turns that into the active run)."""
    run = SheetSyncRun(trigger=trigger, status="QUEUED", source=source_label)
    db.add(run)
    db.flush()
    return run.run_id


def active_run(db: Session) -> SheetSyncRun | None:
    return db.scalars(
        select(SheetSyncRun).where(SheetSyncRun.status.in_(("QUEUED", "RUNNING")))
    ).one_or_none()


def sync_now(source: SheetSource, trigger: str = "MANUAL") -> SyncResult:
    """Create a run and execute it here (tests, CLI, uploads)."""
    with SessionLocal() as db, db.begin():
        run_id = create_run(db, trigger, source.label)
    return execute(run_id, source)


def fail_run(run_id: int, error: str) -> SyncResult:
    """End a run that couldn't start (no Sheet configured, no key)."""
    return _finish(SyncResult(run_id, "FAILED", error), time.monotonic())


def execute(run_id: int, source: SheetSource) -> SyncResult:
    with SessionLocal() as db, db.begin():
        run = db.get_one(SheetSyncRun, run_id, with_for_update=True)
        run.status = "RUNNING"
        run.started_at = datetime.now(UTC)
    started = time.monotonic()
    try:
        tabs = source.read()
    except SourceError as exc:
        return _finish(SyncResult(run_id, "FAILED", str(exc)), started)
    try:
        result = _Engine(run_id).run(tabs)
    except Exception as exc:  # a bug or the database: the run is FAILED, the next one retries
        log.exception("sheet sync run %s failed", run_id)
        return _finish(SyncResult(run_id, "FAILED", f"{type(exc).__name__}: {exc}"[:500]), started)
    return _finish(result, started)


def _finish(result: SyncResult, started: float) -> SyncResult:
    with SessionLocal() as db, db.begin():
        run = db.get_one(SheetSyncRun, result.run_id, with_for_update=True)
        run.status = result.status
        run.error = result.error
        run.finished_at = datetime.now(UTC)
        run.counts = {
            **result.counts,
            "versions": result.versions,
            "seconds": round(time.monotonic() - started, 3),
        }
        changed = result.versions or any(
            d.changed_data or (d.outcome in FLAGS and not d.skipped) for d in result.decisions
        )
        if changed:
            audit.record(
                db,
                None,
                "sheet.sync",
                "sheet_sync_run",
                str(result.run_id),
                after={"source": run.source, "counts": run.counts},
            )
    return result


# --- The engine ------------------------------------------------------------------------------


def _errors_text(fields: dict[str, str]) -> str:
    return "; ".join(f"{name}: {message}" for name, message in fields.items())


class _Engine:
    def __init__(self, run_id: int) -> None:
        self.run_id = run_id
        self.decisions: list[Decision] = []
        self.new_students: list[str] = []
        self.versions = 0

    def run(self, tabs: dict[str, Tab]) -> SyncResult:
        errors = []
        counts: dict[str, dict[str, int]] = {}
        for name, step in ((SKILLS, self._skills), (STUDENTS, self._students)):
            if missing := tabs[name].missing():
                errors.append(f"{name}: missing column{'s' if len(missing) > 1 else ''} "
                              f"{', '.join(missing)}")  # fmt: skip
                continue
            step(tabs[name])
        verified = tabs[VERIFIED]
        if missing := verified.missing():
            errors.append(f"{VERIFIED}: missing column{'s' if len(missing) > 1 else ''} "
                          f"{', '.join(missing)}")  # fmt: skip
        else:
            self._verified(verified)
        self._first_versions()
        self._save()
        failed = {e.split(":")[0] for e in errors}
        for name in TABS:
            if name not in failed:
                counts[name] = dict(Counter(d.outcome for d in self.decisions if d.tab == name))
        return SyncResult(
            run_id=self.run_id,
            status="FAILED" if errors else "DONE",
            error="; ".join(errors) or None,
            counts=counts,
            decisions=self.decisions,
            versions=self.versions,
            verified=verified,
        )

    def _previous(self, db: Session, tab: str) -> dict[str, SheetRecord]:
        return {r.key: r for r in db.scalars(select(SheetRecord).where(SheetRecord.tab == tab))}

    def _fast_path(
        self, tab: str, item: Keyed, digest: str, previous: dict[str, SheetRecord]
    ) -> Decision | None:
        prev = previous.get(item.key)
        if prev is None or prev.row_hash != digest or prev.outcome not in FINAL[tab]:
            return None
        outcome = prev.outcome if tab == VERIFIED else "UNCHANGED"
        return Decision(tab, item.key, item.row.number, digest, outcome, prev.message,
                        prev.award_id, prev.version_id, skipped=True)  # fmt: skip

    # --- Skills Catalog ----------------------------------------------------------------------

    def _skills(self, tab: Tab) -> None:
        with SessionLocal() as db, db.begin():
            previous = self._previous(db, SKILLS)
            for item in keyed_rows(tab):
                digest = row_hash(SKILLS, item.values)
                decision = Decision(SKILLS, item.key, item.row.number, digest, "ERROR")
                if item.first_row is not None:
                    decision.message = f"Same skill code as row {item.first_row}; not applied"
                elif skipped := self._fast_path(SKILLS, item, digest, previous):
                    decision = skipped
                else:
                    try:
                        with db.begin_nested():
                            self._skill(db, item.values, decision)
                    except IntegrityError as exc:
                        decision.outcome = "ERROR"
                        decision.message = f"Could not be saved ({type(exc.orig).__name__})"
                        decision.changed_data = False
                self.decisions.append(decision)

    def _skill(self, db: Session, v: dict[str, str], d: Decision) -> None:
        errors = []
        if not v["skill_code"]:
            errors.append("skill_code is missing")
        elif not SKILL_CODE_RE.match(v["skill_code"]):
            errors.append("skill_code: use SKL- and 3 or more digits, e.g. SKL-017")
        for column, limit in (("name", SKILL_NAME_MAX), ("description", SKILL_DESCRIPTION_MAX)):
            if not v[column]:
                errors.append(f"{column} is missing")
            elif len(v[column]) > limit:
                errors.append(f"{column} is longer than {limit} characters")
        category = None
        if not v["category"]:
            errors.append("category is missing")
        else:
            category = db.scalar(
                select(SkillCategory).where(func.lower(SkillCategory.name) == v["category"].lower())
            )
            if category is None:
                errors.append(f"Unknown category {v['category']}")
            elif v["badge_code"] and v["badge_code"].upper() != category.badge_code:
                errors.append(
                    f"badge_code {v['badge_code'].upper()} doesn't match the category "
                    f"{category.name} ({category.badge_code})"
                )
        if errors:
            d.message = "; ".join(errors)
            return
        assert category is not None
        skill = db.get(Skill, v["skill_code"], with_for_update=True)
        holder = db.scalar(
            select(Skill.skill_id).where(
                func.lower(Skill.name) == v["name"].lower(), Skill.skill_id != v["skill_code"]
            )
        )
        if holder is not None:
            d.message = f"name: Already used by {holder}"
            return
        if skill is None:
            if category.archived_at is not None:
                d.message = f"Category {category.name} is archived"
                return
            values = {
                "skill_id": v["skill_code"],
                "name": v["name"],
                "category_id": category.category_id,
                "description": v["description"],
            }
            db.add(Skill(**values))
            db.flush()
            audit.record(db, None, "sheet.skill.create", "skill", v["skill_code"], after=values)
            d.outcome, d.changed_data = "CREATED", True
            return
        if skill.category_id != category.category_id:
            current = db.get_one(SkillCategory, skill.category_id)
            d.message = (
                f"Category differs from the system ({current.name}); change it in the admin panel"
            )
            return
        changed = {k: v[k] for k in ("name", "description") if getattr(skill, k) != v[k]}
        if not changed:
            d.outcome = "UNCHANGED"
            return
        before = {k: getattr(skill, k) for k in changed}
        for k, value in changed.items():
            setattr(skill, k, value)
        db.flush()
        audit.record(db, None, "sheet.skill.update", "skill", skill.skill_id, before, changed)
        d.outcome, d.message, d.changed_data = "UPDATED", f"{', '.join(changed)} updated", True

    # --- Students ----------------------------------------------------------------------------

    def _students(self, tab: Tab) -> None:
        with SessionLocal() as db, db.begin():
            previous = self._previous(db, STUDENTS)
            for item in keyed_rows(tab):
                digest = row_hash(STUDENTS, item.values)
                decision = Decision(STUDENTS, item.key, item.row.number, digest, "ERROR")
                if item.first_row is not None:
                    decision.message = f"Same Student ID as row {item.first_row}; not applied"
                elif skipped := self._fast_path(STUDENTS, item, digest, previous):
                    decision = skipped
                else:
                    try:
                        with db.begin_nested():
                            self._student(db, item.values, decision)
                    except (IntegrityError, AppError) as exc:
                        decision.outcome = "ERROR"
                        decision.changed_data = False
                        decision.message = (
                            _errors_text(exc.fields) or exc.message
                            if isinstance(exc, AppError)
                            else f"Could not be saved ({type(exc.orig).__name__})"
                        )
                        if decision.key in self.new_students:
                            self.new_students.remove(decision.key)
                self.decisions.append(decision)

    def _student(self, db: Session, v: dict[str, str], d: Decision) -> None:
        values, fields = students.clean_fields(v)
        if fields:
            d.message = _errors_text(fields)
            return
        student = db.get(Student, values["student_id"], with_for_update=True)
        if student is None:
            created = students.create_student(
                db, None, StudentCreate(**values), action="sheet.student.create"
            )
            passport = db.scalars(
                select(Passport).where(Passport.student_id == created.student_id)
            ).one()
            self.new_students.append(created.student_id)
            d.outcome, d.message, d.changed_data = (
                "CREATED",
                f"Passport {passport.passport_id}",
                True,
            )
            return
        passport = db.scalars(
            select(Passport).where(Passport.student_id == student.student_id)
        ).one()
        issued = passport.first_issued_on is not None
        applied: dict[str, str] = {}
        conflicts = []
        for column in ("program", "education_level", "status"):
            if getattr(student, column) != values[column]:
                applied[column] = values[column]
        for column, label, printed in (
            ("first_name", "First name", passport.holder_first_name),
            ("last_name", "Last name", passport.holder_last_name),
        ):
            if getattr(student, column) == values[column]:
                continue
            if issued:  # the name is frozen on issued passports
                conflicts.append(
                    f"{label} differs from the issued passport ({printed}); not applied"
                )
            else:
                applied[column] = values[column]
        if student.email != values["email"]:
            holder = db.scalar(select(Student.student_id).where(Student.email == values["email"]))
            if issued:  # the email is the sign-in identity
                conflicts.append(f"Email differs from the system ({student.email}); not applied")
            elif holder is not None:
                conflicts.append(f"Email already used by {holder}; not applied")
            else:
                applied["email"] = values["email"]
        parts = []
        if applied:
            before = {k: getattr(student, k) for k in applied}
            for k, value in applied.items():
                setattr(student, k, value)
            db.flush()
            if "email" in applied:
                events.link_participants(db, student.student_id, student.email)
            audit.record(db, None, "sheet.student.update", "student", student.student_id,
                         before, applied)  # fmt: skip
            parts.append(f"{', '.join(applied)} updated")
            d.changed_data = True
        parts.extend(conflicts)
        d.outcome = "CONFLICT" if conflicts else "UPDATED" if applied else "UNCHANGED"
        d.message = "; ".join(parts) or None

    # --- Verified Skills ---------------------------------------------------------------------

    def _verified(self, tab: Tab) -> None:
        with SessionLocal() as db:
            previous = self._previous(db, VERIFIED)
            known_students = set(db.scalars(select(Student.student_id)))
            skills = {s.skill_id: s for s in db.scalars(select(Skill))}
            by_record = {
                a.source_record_id: (a, kind)
                for a, kind in db.execute(
                    select(SkillAward, AwardSubmission.kind)
                    .join(
                        AwardSubmission, AwardSubmission.submission_id == SkillAward.submission_id
                    )
                    .where(SkillAward.source_record_id.is_not(None))
                )
            }
            held = {
                (a.student_id, a.skill_id): _holding_label(a, kind, event)
                for a, kind, event in db.execute(
                    select(SkillAward, AwardSubmission.kind, Event.name)
                    .join(
                        AwardSubmission, AwardSubmission.submission_id == SkillAward.submission_id
                    )
                    .outerjoin(Event, Event.event_id == AwardSubmission.event_id)
                )
            }
            first_versions = {
                award_id: (passport_id, version_no, version_id)
                for award_id, passport_id, version_no, version_id in db.execute(
                    select(
                        VersionAward.award_id,
                        PassportVersion.passport_id,
                        PassportVersion.version_no,
                        PassportVersion.version_id,
                    )
                    .join(PassportVersion, PassportVersion.version_id == VersionAward.version_id)
                    .where(VersionAward.award_id.in_([a.award_id for a, _ in by_record.values()]))
                    .order_by(PassportVersion.version_no.desc())
                )
            }
        today = issuance.today()
        new: dict[str, list[tuple[Decision, dict[str, Any]]]] = {}
        for item in keyed_rows(tab):
            v = item.values
            digest = row_hash(VERIFIED, v)
            d = Decision(VERIFIED, item.key, item.row.number, digest, "ERROR")
            self.decisions.append(d)
            if item.first_row is not None:
                d.outcome = "DUPLICATE"
                d.message = f"Same Record ID as row {item.first_row}; counted once"
                continue
            if skipped := self._fast_path(VERIFIED, item, digest, previous):
                self.decisions[-1] = skipped
                continue
            if found := by_record.get(item.key):
                self._already_processed(d, v, item.row, *found, first_versions)
                continue
            status = v["status"]
            if not status:
                d.message = "status is missing"
                continue
            if status not in RECORD_STATUSES:
                d.message = "Status must be CONFIRMED, PENDING or REJECTED"
                continue
            if status == "PENDING":
                d.outcome, d.message = "WAITING", "Waiting for confirmation"
                continue
            if status == "REJECTED":
                d.outcome, d.message = "IGNORED", "Rejected; not added"
                continue
            errors = []
            if not v["record_id"]:
                errors.append("record_id is missing")
            elif not RECORD_ID_RE.match(v["record_id"]):
                errors.append("record_id: use REC- and 4 or more digits, e.g. REC-0101")
            if not v["student_id"]:
                errors.append("student_id is missing")
            elif v["student_id"] not in known_students:
                errors.append(f"Unknown student {v['student_id']}")
            skill = skills.get(v["skill_code"])
            if not v["skill_code"]:
                errors.append("skill_code is missing")
            elif skill is None:
                errors.append(f"Unknown skill {v['skill_code']}")
            elif skill.archived_at is not None:
                errors.append(f"Skill {skill.skill_id} is archived")
            earned = parse_date(item.row.values["date_earned"]) if v["date_earned"] else None
            if not v["date_earned"]:
                errors.append("date_earned is missing")
            elif earned is None:
                errors.append("Date earned must be YYYY-MM-DD or DD.MM.YYYY")
            elif earned > today:
                errors.append("Date earned is in the future")
            if len(v["earned_through"]) > EARNED_THROUGH_MAX:
                errors.append(f"earned_through is longer than {EARNED_THROUGH_MAX} characters")
            if errors:
                d.message = "; ".join(errors)
                continue
            pair = (v["student_id"], v["skill_code"])
            if pair in held:
                d.outcome = "DUPLICATE"
                d.message = f"{pair[0]} already holds {pair[1]} ({held[pair]})"
                continue
            held[pair] = f"record {v['record_id']}"  # a later row for the same skill: duplicate
            new.setdefault(v["student_id"], []).append(
                (
                    d,
                    {
                        "skill_id": v["skill_code"],
                        "date_earned": earned,
                        "earned_through": v["earned_through"] or None,
                        "source_record_id": v["record_id"],
                    },
                )
            )
        for student_id in sorted(new):
            self._award(student_id, new[student_id])

    def _already_processed(
        self,
        d: Decision,
        v: dict[str, str],
        row: Row,
        award: SkillAward,
        kind: str,
        first_versions: dict[int, tuple[str, int, int]],
    ) -> None:
        """A record that already has its award: compare, flag edits (D6, D7), never apply."""
        d.award_id = award.award_id
        changes = [
            f"{column} {old} → {new or '(empty)'}"
            for column, old, new in (
                ("student_id", award.student_id, v["student_id"]),
                ("skill_code", award.skill_id, v["skill_code"]),
                ("date_earned", award.date_earned.isoformat(), v["date_earned"]),
                ("earned_through", award.earned_through or "", v["earned_through"]),
            )
            if old != new
        ]
        if v["status"] == "REJECTED":
            d.outcome = "REVOKED_IN_SHEET"
            d.message = (
                "Processed earlier, now REJECTED in the Sheet. The skill stays on the passport "
                "(no automatic revocation); an admin decides"
            )
            return
        if v["status"] != "CONFIRMED":
            changes.append(f"status CONFIRMED → {v['status'] or '(empty)'}")
        if changes:
            d.outcome = "CHANGED_AFTER_PROCESSING"
            d.message = f"Edited after processing ({', '.join(changes)}); not applied"
            return
        if kind != "SHEET":
            d.outcome, d.message = "DUPLICATE", f"Already on the passport ({kind.lower()} import)"
            return
        d.outcome = "PROCESSED"
        if first := first_versions.get(award.award_id):
            passport_id, version_no, version_id = first
            d.version_id = version_id
            d.message = f"Added to {passport_id} v{version_no}"

    def _award(self, student_id: str, items: list[tuple[Decision, dict[str, Any]]]) -> None:
        """One transaction per student: a SHEET submission, the awards, one new version."""
        try:
            with SessionLocal() as db, db.begin():
                submission = AwardSubmission(
                    kind="SHEET", reason=f"Google Sheets sync {self.run_id}"
                )
                db.add(submission)
                db.flush()
                added = []
                for d, values in items:
                    award_id = db.scalar(
                        insert(SkillAward)
                        .values(
                            student_id=student_id, submission_id=submission.submission_id, **values
                        )
                        .on_conflict_do_nothing()
                        .returning(SkillAward.award_id)
                    )
                    if award_id is None:  # awarded concurrently through the panel or an event
                        d.outcome = "DUPLICATE"
                        d.message = f"{student_id} already holds {values['skill_id']}"
                        continue
                    d.award_id = award_id
                    added.append((d, values))
                version = None
                if added:
                    [created] = issuance.create_versions(db, [student_id])
                    version = db.get_one(PassportVersion, created.version_id)
                    self.versions += 1
                    for d, _ in added:
                        d.outcome = "PROCESSED"
                        d.version_id = version.version_id
                        d.message = f"Added to {version.passport_id} v{version.version_no}"
                        d.changed_data = True
                    audit.record(
                        db,
                        None,
                        "sheet.award",
                        "award_submission",
                        str(submission.submission_id),
                        after={
                            "student_id": student_id,
                            "records": [v["source_record_id"] for _, v in added],
                            "skills": [v["skill_id"] for _, v in added],
                            "passport_id": version.passport_id,
                            "version_no": version.version_no,
                            "run_id": self.run_id,
                        },
                    )
                else:
                    db.delete(submission)
                _upsert(db, [d for d, _ in items], self.run_id)
        except Exception as exc:
            log.exception("sheet sync run %s: awards for %s failed", self.run_id, student_id)
            for d, _ in items:
                d.outcome = "ERROR"
                d.message = (
                    f"Could not be processed ({type(exc).__name__}); retried on the next sync"
                )
                d.award_id = d.version_id = None
                d.changed_data = False
            return
        for d, _ in items:
            d.saved = True

    def _first_versions(self) -> None:
        """D5: a student created by this run without a record processed in it still gets V1."""
        for student_id in self.new_students:
            with SessionLocal() as db, db.begin():
                has_version = db.scalar(
                    select(func.count())
                    .select_from(PassportVersion)
                    .join(Passport, Passport.passport_id == PassportVersion.passport_id)
                    .where(Passport.student_id == student_id)
                )
                if not has_version:
                    issuance.create_versions(db, [student_id])
                    self.versions += 1

    def _save(self) -> None:
        with SessionLocal() as db, db.begin():
            _upsert(db, [d for d in self.decisions if not d.saved], self.run_id)


def _holding_label(award: SkillAward, kind: str, event_name: str | None) -> str:
    if kind == "SEED":
        return f"seed import {award.source_record_id}"
    if kind == "SHEET":
        return f"record {award.source_record_id}"
    if kind == "EVENT":
        return f"event {event_name or '(deleted)'}"
    return "direct award"


def _upsert(db: Session, decisions: list[Decision], run_id: int) -> None:
    """Write the decisions that differ from what sheet_records holds. `decided_at` moves only
    when the outcome or message changes (it is the `synced_at` written back to the Sheet)."""
    if not decisions:
        return
    keys = [(d.tab, d.key) for d in decisions]
    stored = {
        (r.tab, r.key): r
        for r in db.scalars(
            select(SheetRecord).where(tuple_(SheetRecord.tab, SheetRecord.key).in_(keys))
        )
    }
    now = datetime.now(UTC)
    for d in decisions:
        r = stored.get((d.tab, d.key))
        if r is None:
            db.add(
                SheetRecord(
                    tab=d.tab,
                    key=d.key,
                    row_number=d.row,
                    row_hash=d.row_hash,
                    outcome=d.outcome,
                    message=d.message,
                    award_id=d.award_id,
                    version_id=d.version_id,
                    first_seen_at=now,
                    decided_at=now,
                    run_id=run_id,
                )
            )
            continue
        if (r.outcome, r.message) != (d.outcome, d.message):
            r.decided_at = now
            r.run_id = run_id
        r.outcome, r.message, r.row_number, r.row_hash = d.outcome, d.message, d.row, d.row_hash
        r.award_id, r.version_id = d.award_id, d.version_id
    db.flush()
