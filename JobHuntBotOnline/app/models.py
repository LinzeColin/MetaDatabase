from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email_lookup: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    display_name_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    auth_version: Mapped[int] = mapped_column(Integer, default=1)
    daily_ai_request_limit: Mapped[int] = mapped_column(Integer, default=60)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    auth_version: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EmailToken(Base):
    __tablename__ = "email_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(32), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EmailDelivery(Base):
    __tablename__ = "email_deliveries"
    __table_args__ = (
        Index(
            "ix_email_deliveries_recipient_lookup_created_at",
            "recipient_lookup",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    # This is the existing HMAC lookup, never an email address.  It keeps the
    # recipient delivery limit enforceable after a user deletes their account.
    recipient_lookup: Mapped[str | None] = mapped_column(String(64), nullable=True)
    kind: Mapped[str] = mapped_column(String(32))
    recipient_masked: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(24))
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RateLimitBucket(Base):
    __tablename__ = "rate_limit_buckets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bucket_key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    window_started_at: Mapped[datetime] = mapped_column(DateTime)
    count: Mapped[int] = mapped_column(Integer, default=0)


class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    payload_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    onboarding_state: Mapped[str] = mapped_column(String(32), default="needs_resume", index=True)
    discovery_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    next_discovery_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_discovery_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Resume(Base):
    __tablename__ = "resumes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    original_name_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    storage_name: Mapped[str] = mapped_column(String(80), unique=True)
    text_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    parsed_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    content_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Experience(Base):
    __tablename__ = "experiences"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    detail_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    kind: Mapped[str] = mapped_column(String(32), default="experience")
    strength: Mapped[str] = mapped_column(String(16), default="medium")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(48), index=True)
    external_id: Mapped[str] = mapped_column(String(255))
    canonical_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(255), index=True)
    company: Mapped[str] = mapped_column(String(255), index=True)
    location: Mapped[str] = mapped_column(String(255), default="")
    city: Mapped[str] = mapped_column(String(120), default="", index=True)
    country: Mapped[str] = mapped_column(String(8), default="", index=True)
    work_mode: Mapped[str] = mapped_column(String(24), default="", index=True)
    role_family: Mapped[str] = mapped_column(String(80), default="", index=True)
    industry: Mapped[str] = mapped_column(String(80), default="", index=True)
    skills_text: Mapped[str] = mapped_column(Text, default="")
    keywords_text: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_jobs_source_external"),
        Index("ix_jobs_open_recent", "closed_at", "posted_at"),
    )


class Recommendation(Base):
    __tablename__ = "recommendations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    qualification: Mapped[str] = mapped_column(String(16), index=True)
    relevance: Mapped[str] = mapped_column(String(16), index=True)
    opportunity: Mapped[str] = mapped_column(String(16), index=True)
    rank_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    reasons_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    user_status: Mapped[str] = mapped_column(String(24), default="new", index=True)
    first_recommended_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_scored_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_recommendation_user_job"),)


class DiscoveryRun(Base):
    __tablename__ = "discovery_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    trigger: Mapped[str] = mapped_column(String(24), default="scheduled")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    jobs_seen: Mapped[int] = mapped_column(Integer, default=0)
    jobs_new: Mapped[int] = mapped_column(Integer, default=0)
    recommendations_updated: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class DiscoverySourceStatus(Base):
    __tablename__ = "discovery_source_status"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("discovery_runs.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(48), index=True)
    status: Mapped[str] = mapped_column(String(24))
    jobs_seen: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ApplicationPack(Base):
    __tablename__ = "application_packs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    content_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    resume_id: Mapped[int | None] = mapped_column(ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)


class ApplicationProgress(Base):
    """The editable current state for one user's application to one job.

    Immutable snapshots of each revision remain in ``ApplicationEvent`` so a
    correction never erases the truthful application history.
    """

    __tablename__ = "application_progresses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    evidence_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    notes_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_application_progresses_user_job"),)


class ApplicationEvent(Base):
    __tablename__ = "application_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    evidence_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    notes_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    action: Mapped[str] = mapped_column(String(24), default="recorded")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class AIUsage(Base):
    __tablename__ = "ai_usage"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope_key: Mapped[str] = mapped_column(String(80), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    day_key: Mapped[str] = mapped_column(String(10), index=True)
    requests: Mapped[int] = mapped_column(Integer, default=0)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint("scope_key", "day_key", name="uq_ai_usage_scope_day"),)


class PlatformState(Base):
    __tablename__ = "platform_state"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
