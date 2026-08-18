from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from social_archive.title_repair import is_playback_timestamp, undouble_title

ArchiveLevel = Literal["L0", "L1", "L2", "L3"]
RelationType = Literal["manual_save", "bookmark", "saved", "favorite", "like", "upvoted", "watch_later", "history", "collection"]


class CaptureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    platform: str = Field(min_length=1, max_length=64)
    url: HttpUrl
    external_content_id: str | None = Field(default=None, max_length=512)
    relation_type: RelationType = "manual_save"
    collection_key: str = Field(default="", max_length=512)
    # The browser account mirror labels every scanned item with the collection
    # it came from. CaptureRequest forbids unknown fields, so an undeclared
    # collection_name made the server reject the whole batch with 422 and the
    # mirror imported nothing at all -- items were found and sent, then thrown
    # away at the door. Collection registration still happens once per batch in
    # account_sync; this field only has to be accepted, not re-processed.
    collection_name: str | None = Field(default=None, max_length=512)
    title: str | None = Field(default=None, max_length=2048)
    author_name: str | None = Field(default=None, max_length=1024)
    text: str | None = Field(default=None, max_length=2_000_000)
    published_at: str | None = None
    relation_observed_at: str | None = None
    topic: str | None = Field(default=None, max_length=256)
    keywords: list[str] = Field(default_factory=list, max_length=32)
    language: str | None = Field(default=None, max_length=32)
    media_urls: list[HttpUrl] = Field(default_factory=list, max_length=100)
    source_account_id: str | None = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
    requested_levels: list[ArchiveLevel] = Field(default_factory=lambda: ["L0", "L1", "L3"])
    destination_ids: list[str] = Field(default_factory=lambda: ["social_archive"], max_length=8)

    @field_validator("title")
    @classmethod
    def a_playback_timestamp_is_not_a_title(cls, value: str | None) -> str | None:
        """`06:26/12:57` 是播放器上的时间，不是标题——**置空，别存**。

        2026-08-12 生产实测：他 193 条里有 56 条是这样，全部来自 B 站 history
        那条路，占他 B 站条目的一半以上。打开 Obsidian 一眼望去认不出是什么。

        **置空而不是拒绝整条**：拒绝的话那条内容根本进不来，他丢的是内容本身，
        比标题错更糟。置空之后界面有兜底（`item.title || _urlLabel(...)`），
        他看到的是链接尾巴——不好看，但至少是真的。

        而且 `title=COALESCE(excluded.title, content.title)` 遇到 NULL 会**保住
        库里已有的好标题**，所以这道门顺带让「把那 56 条修回真标题」修得住：
        下一次 history 同步不会再把它冲回播放进度。

        **这不代表取数侧修好了**：真标题在历史页的哪个元素上，仍然要等他
        登录之后的那一页。这道门只保证「错的东西进不来」，不保证「对的东西进得来」。
        """
        if value is None:
            return None
        # **判定搬到 `title_repair` 里了**：这里原来自己写了一份 `\d{1,2}:\d{2}`，
        # 认不出长视频那种带小时的（`01:11:19/01:15:32`）。他库里 6 条这样的
        # 标题，两处判据只认出 1 条，另外 5 条一路绿到底。一份文本一把尺子。
        if is_playback_timestamp(value):
            return None
        return value

    @field_validator("title")
    @classmethod
    def a_title_scraped_twice_gets_one_copy(cls, value: str | None) -> str | None:
        """`23.0万极限三选一…极限三选一…` → `极限三选一…`。判据见 `title_repair`。

        **这一条修，不像上面那条置空**——因为真标题就在这串里，重复本身就是证据，
        不用联网也不用他登录。置空反而把已经拿到的东西扔了。

        生产实测 11 条，全部是抖音。光修库里的存量不够：下一次抖音同步会照原样
        再写一遍，所以判据要摆在入口这里，存量修复只是把过去那批补上。
        """
        return undouble_title(value)

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
    cursor: str | None = Field(default=None, max_length=1024)
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


# Account-mirror requests deliberately carry only opaque connection references
# and normalized public metadata.  They never accept cookies, passwords or
# authorization headers as part of the capture protocol.
AccountAuthMethod = Literal[
    "oauth",
    "qr",
    "browser_session",
    "official_export",
    "local_import",
    "chrome_bookmarks",
]
SyncMode = Literal["first_full", "incremental", "manual_repair", "official_import", "browser_import"]


class AccountConnectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    platform: str = Field(min_length=1, max_length=64)
    auth_method: AccountAuthMethod
    display_name: str | None = Field(default=None, max_length=256)
    external_account_id: str | None = Field(default=None, max_length=512)
    auto_sync_enabled: bool = True
    sync_interval_minutes: int = Field(default=360, ge=15, le=10080)
    relation_types: list[RelationType] = Field(default_factory=list, max_length=16)


class AccountConnectCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    connection_ref: str = Field(min_length=8, max_length=2048)
    external_account_id: str = Field(min_length=1, max_length=512)
    display_name: str | None = Field(default=None, max_length=256)
    verified: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class AccountSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: SyncMode = "incremental"
    relation_types: list[RelationType] = Field(default_factory=list, max_length=16)
    trigger_type: Literal["manual", "scheduled", "scheduled_server", "first_connect", "recovery",
    "bookmark_change", "resume", "retry"] = "manual"


class SyncBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relation_type: RelationType
    collection_key: str = Field(default="", max_length=512)
    collection_name: str | None = Field(default=None, max_length=512)
    external_collection_id: str | None = Field(default=None, max_length=512)
    items: list[CaptureRequest] = Field(default_factory=list, max_length=250)
    # Collection/page chunks never imply completion for the whole relation.
    # A separate relation-final batch is required before absence closure can run.
    scope_type: Literal["collection", "relation"] = "relation"
    batch_index: int = Field(default=0, ge=0)
    batch_count: int | None = Field(default=None, ge=1)
    completeness: Literal["complete", "partial", "failed", "unknown"] = "partial"
    cursor: dict[str, Any] = Field(default_factory=dict)
    known_anchor: str | None = Field(default=None, max_length=2048)
    has_more: bool = False
    failure_code: str | None = Field(default=None, max_length=256)


class SyncControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["pause", "resume", "cancel", "retry"]
