"""Passport versions, their awards, and the Merkle batches that anchor them."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BATCH_STATUSES, VERSION_STATUSES, Base, created_at, one_of


class PassportVersion(Base):
    __tablename__ = "passport_versions"
    __table_args__ = (
        UniqueConstraint("passport_id", "version_no"),
        CheckConstraint("version_no >= 1", name="version_no_positive"),
        one_of("status", VERSION_STATUSES),
    )

    version_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    passport_id: Mapped[str] = mapped_column(ForeignKey("passports.passport_id"))
    version_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text)
    content_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # frozen once RENDERED
    verification_code: Mapped[str | None] = mapped_column(Text, unique=True)
    pdf_sha256: Mapped[str | None] = mapped_column(Text, unique=True)
    pdf_key: Mapped[str | None] = mapped_column(Text)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("anchor_batches.batch_id"))
    merkle_proof: Mapped[list[str] | None] = mapped_column(JSONB)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()


class VersionAward(Base):
    __tablename__ = "version_awards"

    version_id: Mapped[int] = mapped_column(
        ForeignKey("passport_versions.version_id"), primary_key=True
    )
    award_id: Mapped[int] = mapped_column(ForeignKey("skill_awards.award_id"), primary_key=True)


class AnchorBatch(Base):
    __tablename__ = "anchor_batches"
    __table_args__ = (one_of("status", BATCH_STATUSES),)

    batch_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    merkle_root: Mapped[str] = mapped_column(Text, unique=True)
    leaf_count: Mapped[int] = mapped_column(Integer)
    chain_id: Mapped[int] = mapped_column(BigInteger)
    contract_address: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
    tx_hash: Mapped[str | None] = mapped_column(Text)
    block_number: Mapped[int | None] = mapped_column(BigInteger)
    anchored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at()
