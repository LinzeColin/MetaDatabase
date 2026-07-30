from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

ArchiveLevel = Literal["L0", "L1", "L2", "L3"]
RelationType = Literal["manual_save", "bookmark", "saved", "favorite", "like", "upvoted", "watch_later", "history", "collection"]


class CaptureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    platform: str = Field(min_length=1, max_length=64)
    url: HttpUrl
    external_content_id: str | None = Field(default=None, max_length=512)
    relation_type: RelationType = "manual_save"
    collection_key: str = Field(default="", max_length=512)
    title: str | None = Field(default=None, max_length=2048)
    author_name: str | None = Field(default=None, max_length=1024)
    text: str | None = Field(default=None, max_length=2_000_000)
    published_at: str | None = None
    media_urls: list[HttpUrl] = Field(default_factory=list, max_length=100)
    source_account_id: str | None = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
    requested_levels: list[ArchiveLevel] = Field(default_factory=lambda: ["L0", "L1", "L3"])
    destination_ids: list[str] = Field(default_factory=lambda: ["social_archive"], max_length=8)

    @field_validator("requested_levels")
    @classmethod
    def unique_levels(cls, value: list[ArchiveLevel]) -> list[ArchiveLevel]:
        return list(dict.fromkeys(value))

    @field_validator("destination_ids")
    @classmethod
    def unique_destinations(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip().lower() for item in value if item and item.strip()]
        result = list(dict.fromkeys(cleaned))
        if "social_archive" not in result:
            result.insert(0, "social_archive")
        return result[:8]


class CaptureBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[CaptureRequest] = Field(min_length=1, max_length=100)


class CaptureResponse(BaseModel):
    content_id: str
    relation_id: str
    observation_id: str
    job_ids: list[str]
    skipped_destination_ids: list[str] = Field(default_factory=list)
    accepted_levels: list[ArchiveLevel]
    paused_levels: list[ArchiveLevel]
    detail_url: str


class MarkdownImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root: str | None = None
    platform_hint: str = "import"
    relation_type: RelationType = "saved"
    limit: int = Field(default=1000, ge=1, le=10000)


class ConnectorRunRequest(BaseModel):
    """One safe, read-only connector action. Credentials are never accepted in the body."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    relation_type: RelationType | None = None
    url: HttpUrl | None = None
    limit: int = Field(default=20, ge=1, le=100)
    collection_key: str = Field(default="", max_length=512)
    source_account_id: str | None = Field(default=None, max_length=512)
    requested_levels: list[ArchiveLevel] = Field(default_factory=lambda: ["L0", "L1", "L3"])
    destination_ids: list[str] = Field(default_factory=lambda: ["social_archive"], max_length=8)

    @field_validator("requested_levels")
    @classmethod
    def unique_connector_levels(cls, value: list[ArchiveLevel]) -> list[ArchiveLevel]:
        return list(dict.fromkeys(value))

    @field_validator("destination_ids")
    @classmethod
    def unique_connector_destinations(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip().lower() for item in value if item and item.strip()]
        result = list(dict.fromkeys(cleaned))
        if "social_archive" not in result:
            result.insert(0, "social_archive")
        return result[:8]


class ConnectorStateView(BaseModel):
    connector_id: str
    display_name: str
    state: Literal["healthy", "degraded", "paused", "disabled", "blocked_environment"]
    policy_gate: str
    auth_gate: str
    technical_gate: str
    last_success_at: str | None = None
    last_error_code: str | None = None
    next_action_zh: str


class JobView(BaseModel):
    id: str
    job_type: str
    connector_id: str | None
    status: str
    attempt_count: int
    created_at: str
    updated_at: str
    last_error_code: str | None = None
    last_error_message: str | None = None
