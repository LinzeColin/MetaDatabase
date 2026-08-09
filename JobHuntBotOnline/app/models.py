from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.db_types import EncryptedBoolean, EncryptedInteger, EncryptedText


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), default="Owner", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    session_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"
    __table_args__ = (UniqueConstraint("user_id", name="uq_candidate_profile_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    preferred_name: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    legal_name: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    email: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    phone: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    current_location: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    linkedin_url: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    github_url: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    portfolio_url: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    current_status: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    work_authorization_country: Mapped[str] = mapped_column(EncryptedText(), default="Australia", nullable=False)
    work_authorization_text: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    sponsorship_now: Mapped[bool | None] = mapped_column(EncryptedBoolean(), nullable=True)
    sponsorship_future: Mapped[bool | None] = mapped_column(EncryptedBoolean(), nullable=True)
    target_roles_json: Mapped[str] = mapped_column(EncryptedText(), default="[]", nullable=False)
    secondary_roles_json: Mapped[str] = mapped_column(EncryptedText(), default="[]", nullable=False)
    roles_to_avoid_json: Mapped[str] = mapped_column(EncryptedText(), default="[]", nullable=False)
    industries_to_avoid_json: Mapped[str] = mapped_column(EncryptedText(), default="[]", nullable=False)
    target_locations_json: Mapped[str] = mapped_column(EncryptedText(), default="[]", nullable=False)
    work_mode: Mapped[str] = mapped_column(EncryptedText(), default="Hybrid / Onsite / Remote", nullable=False)
    relocation_policy: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    target_level: Mapped[str] = mapped_column(EncryptedText(), default="Graduate / Entry level", nullable=False)
    graduation_year: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    professional_experience_years: Mapped[int | None] = mapped_column(EncryptedInteger(), nullable=True)
    degree_summary: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    available_start_date: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    salary_strategy: Mapped[str] = mapped_column(
        EncryptedText(), default="Prefer not to state; use confirmed range only when required.", nullable=False
    )
    salary_range: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    self_identification_strategy: Mapped[str] = mapped_column(
        EncryptedText(), default="prefer_not_to_say", nullable=False
    )
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    @property
    def target_roles(self) -> list[str]:
        return json_loads(self.target_roles_json, [])

    @property
    def secondary_roles(self) -> list[str]:
        return json_loads(self.secondary_roles_json, [])

    @property
    def roles_to_avoid(self) -> list[str]:
        return json_loads(self.roles_to_avoid_json, [])

    @property
    def industries_to_avoid(self) -> list[str]:
        return json_loads(self.industries_to_avoid_json, [])

    @property
    def target_locations(self) -> list[str]:
        return json_loads(self.target_locations_json, [])


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    role_family: Mapped[str] = mapped_column(EncryptedText(), default="General", nullable=False)
    source_filename: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    file_type: Mapped[str] = mapped_column(String(40), nullable=False)
    encrypted_file_path: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    extracted_text: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    skills_json: Mapped[str] = mapped_column(EncryptedText(), default="[]", nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    @property
    def skills(self) -> list[str]:
        return json_loads(self.skills_json, [])


class Experience(Base):
    __tablename__ = "experiences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    resume_id: Mapped[int | None] = mapped_column(
        ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    category: Mapped[str] = mapped_column(String(40), default="experience", nullable=False)
    title: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    organization: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    date_range: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    description: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    tags_json: Mapped[str] = mapped_column(EncryptedText(), default="[]", nullable=False)
    source_ref: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    @property
    def tags(self) -> list[str]:
        return json_loads(self.tags_json, [])


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(2000), default="", nullable=False)
    source: Mapped[str] = mapped_column(String(160), default="Manual", nullable=False)
    company: Mapped[str] = mapped_column(String(240), default="Unknown company", nullable=False)
    title: Mapped[str] = mapped_column(String(300), default="Unknown role", nullable=False)
    location: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    posted_date: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(60), default="Needs review", nullable=False, index=True)
    recommendation: Mapped[str] = mapped_column(String(60), default="Review", nullable=False)
    fit_label: Mapped[str] = mapped_column(String(60), default="Unknown", nullable=False)
    eligibility_status: Mapped[str] = mapped_column(String(60), default="Unknown", nullable=False)
    freshness_status: Mapped[str] = mapped_column(String(60), default="Unknown", nullable=False)
    application_effort: Mapped[str] = mapped_column(String(60), default="Unknown", nullable=False)
    reasons_json: Mapped[str] = mapped_column(EncryptedText(), default="[]", nullable=False)
    risks_json: Mapped[str] = mapped_column(EncryptedText(), default="[]", nullable=False)
    unknowns_json: Mapped[str] = mapped_column(EncryptedText(), default="[]", nullable=False)
    matched_skills_json: Mapped[str] = mapped_column(EncryptedText(), default="[]", nullable=False)
    missing_skills_json: Mapped[str] = mapped_column(EncryptedText(), default="[]", nullable=False)
    selected_resume_id: Mapped[int | None] = mapped_column(
        ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    next_action: Mapped[str] = mapped_column(EncryptedText(), default="Review recommendation", nullable=False)
    next_action_date: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    current_stage: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    notes: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    @property
    def reasons(self) -> list[str]:
        return json_loads(self.reasons_json, [])

    @property
    def risks(self) -> list[str]:
        return json_loads(self.risks_json, [])

    @property
    def unknowns(self) -> list[str]:
        return json_loads(self.unknowns_json, [])

    @property
    def matched_skills(self) -> list[str]:
        return json_loads(self.matched_skills_json, [])

    @property
    def missing_skills(self) -> list[str]:
        return json_loads(self.missing_skills_json, [])


class ApplicationPack(Base):
    __tablename__ = "application_packs"
    __table_args__ = (UniqueConstraint("job_id", name="uq_application_pack_job"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    resume_id: Mapped[int | None] = mapped_column(
        ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True
    )
    experience_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    fit_summary: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    why_role_draft: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    why_company_draft: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    work_authorization_answer: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    sponsorship_answer: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    salary_answer: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    checklist_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    user_reviewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    @property
    def experience_ids(self) -> list[int]:
        return json_loads(self.experience_ids_json, [])

    @property
    def checklist(self) -> list[str]:
        return json_loads(self.checklist_json, [])


class AIProviderConfig(Base):
    __tablename__ = "ai_provider_configs"
    __table_args__ = (UniqueConstraint("user_id", name="uq_ai_provider_config_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(40), default="deepseek", nullable=False)
    api_key: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    base_url: Mapped[str] = mapped_column(String(300), default="https://api.deepseek.com", nullable=False)
    fast_model: Mapped[str] = mapped_column(String(100), default="deepseek-v4-flash", nullable=False)
    precision_model: Mapped[str] = mapped_column(String(100), default="deepseek-v4-pro", nullable=False)
    default_mode: Mapped[str] = mapped_column(String(20), default="fast", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consent_to_external_processing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    daily_request_limit: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    daily_token_limit: Mapped[int] = mapped_column(Integer, default=600000, nullable=False)
    max_input_characters: Mapped[int] = mapped_column(Integer, default=60000, nullable=False)
    request_timeout_seconds: Mapped[int] = mapped_column(Integer, default=75, nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    circuit_open_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class AIApplicationEnhancement(Base):
    __tablename__ = "ai_application_enhancements"
    __table_args__ = (UniqueConstraint("job_id", name="uq_ai_enhancement_job"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(40), default="deepseek", nullable=False)
    model: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    mode: Mapped[str] = mapped_column(String(20), default="fast", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="not_run", nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), default="job-analysis-v2", nullable=False)
    content_json: Mapped[str] = mapped_column(EncryptedText(), default="{}", nullable=False)
    usage_json: Mapped[str] = mapped_column(EncryptedText(), default="{}", nullable=False)
    error_message: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    @property
    def content(self) -> dict[str, Any]:
        return json_loads(self.content_json, {})

    @property
    def usage(self) -> dict[str, Any]:
        return json_loads(self.usage_json, {})


class AIUsageRecord(Base):
    __tablename__ = "ai_usage_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    operation: Mapped[str] = mapped_column(String(80), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), default="deepseek", nullable=False)
    model: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    mode: Mapped[str] = mapped_column(String(20), default="fast", nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class JobEvent(Base):
    __tablename__ = "job_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    note: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    object_type: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    object_id: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    details_json: Mapped[str] = mapped_column(EncryptedText(), default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    payload_json: Mapped[str] = mapped_column(EncryptedText(), default="{}", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BackupRecord(Base):
    __tablename__ = "backup_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="created", nullable=False)
    note: Mapped[str] = mapped_column(EncryptedText(), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class SystemState(Base):
    __tablename__ = "system_state"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
