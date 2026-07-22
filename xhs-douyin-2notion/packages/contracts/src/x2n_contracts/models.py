"""Version 1.0 x2n contracts.

The module intentionally contains contracts and deterministic validation only. It
does not open files, spawn processes, access a browser, create jobs, or write a DB.
"""

from __future__ import annotations

import hmac
import json
import re
from collections import deque
from collections.abc import Mapping
from enum import Enum
from typing import Annotated, Any, Literal, Union
from uuid import UUID

from pydantic import (
    ConfigDict,
    Field,
    RootModel,
    StringConstraints,
    ValidationError,
    model_validator,
)

from .base import (
    CONTRACT_VERSION,
    RFC3339DateTime,
    StrictContract,
    canonical_json_sha256,
    validate_canonical_page_url,
)
from .errors import DataEffect, ERROR_SPECS, ErrorClass, ErrorCode, NextAction

SchemaVersion = Literal["1.0"]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
SafeToken = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")]
PlatformContentId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,191}$")]
OpaqueRef = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._-]{0,191}$")]
ContractKey = Annotated[str, StringConstraints(min_length=3, max_length=768)]
PrivateText = Annotated[str, StringConstraints(min_length=1, max_length=20_000)]
ShortText = Annotated[str, StringConstraints(min_length=1, max_length=500)]


class Platform(str, Enum):
    XIAOHONGSHU = "xiaohongshu"
    DOUYIN = "douyin"
    BILIBILI = "bilibili"
    KUAISHOU = "kuaishou"
    WEIBO = "weibo"
    TAOBAO = "taobao"


class ContentType(str, Enum):
    TEXT = "text"
    IMAGE_GALLERY = "image_gallery"
    VIDEO = "video"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class ContentStatus(str, Enum):
    ACTIVE = "active"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"
    DELETED_BY_USER = "deleted_by_user"


class RelationType(str, Enum):
    LIKED = "liked"
    FAVORITED = "favorited"
    SAVED_CURRENT = "saved_current"


class RelationStatus(str, Enum):
    ACTIVE = "active"
    UNKNOWN = "unknown"
    TOMBSTONE_CANDIDATE = "tombstone_candidate"
    REMOVED = "removed"


class ConfirmationSource(str, Enum):
    SCAN = "scan"
    OWNER = "owner"


class ArtifactType(str, Enum):
    TRANSCRIPT = "transcript"
    OCR = "ocr"
    VISION = "vision"
    FUSION_SUMMARY = "fusion_summary"
    SEARCH_TEXT = "search_text"


class SinkKind(str, Enum):
    MARKDOWN = "markdown"
    NOTION = "notion"


class NativeAction(str, Enum):
    CAPTURE_CURRENT = "capture_current"
    START_SYNC = "start_sync"
    GET_JOB = "get_job"
    CANCEL_JOB = "cancel_job"
    RETRY_JOB = "retry_job"
    GET_CAPABILITIES = "get_capabilities"
    HEALTH = "health"


class DuplicateDisposition(str, Enum):
    NEW_REQUEST = "new_request"
    RETURN_EXISTING_JOB = "return_existing_job"
    REJECT_CONFLICT = "reject_conflict"


def build_content_key(platform: Platform | str, platform_content_id: str) -> str:
    platform_value = platform.value if isinstance(platform, Platform) else platform
    if platform_value not in {item.value for item in Platform}:
        raise ValueError("unsupported platform")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,191}", platform_content_id) is None:
        raise ValueError("invalid platform content id")
    return f"{platform_value}:{platform_content_id}"


def build_relation_key(
    account_ref_hash: str,
    content_key: str,
    relation_type: RelationType | str,
    source_collection_id: str | None = None,
) -> str:
    relation_value = relation_type.value if isinstance(relation_type, RelationType) else relation_type
    parts = [account_ref_hash, content_key, relation_value]
    if source_collection_id is not None:
        parts.append(source_collection_id)
    return ":".join(parts)


def build_artifact_key(
    content_key: str,
    artifact_type: ArtifactType | str,
    input_hash: str,
    processor_version: str,
) -> str:
    artifact_value = artifact_type.value if isinstance(artifact_type, ArtifactType) else artifact_type
    return ":".join((content_key, artifact_value, input_hash, processor_version))


def build_sink_key(sink: SinkKind | str, content_key: str, sink_schema_version: str) -> str:
    sink_value = sink.value if isinstance(sink, SinkKind) else sink
    return ":".join((sink_value, content_key, sink_schema_version))


class ErrorContract(StrictContract):
    schema_version: SchemaVersion
    code: ErrorCode
    error_class: ErrorClass = Field(alias="class")
    retryable: bool
    safe_message: ShortText
    internal_ref: Annotated[str, StringConstraints(pattern=r"^evt_[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")]
    data_effect: DataEffect
    next_action: NextAction

    @model_validator(mode="after")
    def registry_values_match(self) -> "ErrorContract":
        spec = ERROR_SPECS[self.code]
        actual = (self.error_class, self.retryable, self.data_effect, self.next_action)
        expected = (spec.error_class, spec.retryable, spec.data_effect, spec.next_action)
        if actual != expected:
            raise ValueError("error fields do not match the stable registry")
        return self


class PageContext(StrictContract):
    content_id: PlatformContentId
    title: Annotated[str, StringConstraints(max_length=500)] | None = None
    content_type: ContentType


class CaptureCurrentPayload(StrictContract):
    platform: Platform
    page_url: Annotated[str, StringConstraints(min_length=9, max_length=2_048)]
    page_context: PageContext
    relation: RelationType
    category_id: UUID | None = None
    user_gesture: Literal[True]
    auto_scroll: Literal[False]
    change_account_state: Literal[False]

    @model_validator(mode="after")
    def page_url_is_canonical(self) -> "CaptureCurrentPayload":
        validate_canonical_page_url(self.page_url, self.platform)
        if self.relation is not RelationType.SAVED_CURRENT:
            raise ValueError("capture_current must use saved_current relation")
        return self


class StartSyncPayload(StrictContract):
    platform: Platform
    relation: RelationType
    source_collection_id: SafeToken | None = None
    max_items: Annotated[int, Field(ge=1, le=80)]
    user_gesture: Literal[True]
    bounded_batch: Literal[True]
    auto_scroll: Literal[False]
    change_account_state: Literal[False]

    @model_validator(mode="after")
    def relation_is_list_relation(self) -> "StartSyncPayload":
        if self.relation is RelationType.SAVED_CURRENT:
            raise ValueError("start_sync cannot use saved_current relation")
        return self


class JobPayload(StrictContract):
    job_id: UUID


class EmptyPayload(StrictContract):
    pass


class NativeRequestBase(StrictContract):
    schema_version: SchemaVersion
    request_id: UUID
    sent_at: RFC3339DateTime
    payload_hash: Sha256

    @model_validator(mode="before")
    @classmethod
    def payload_hash_matches_wire_payload(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            raise ValueError("native request must be an object")
        payload = value.get("payload")
        supplied = value.get("payload_hash")
        if not isinstance(payload, Mapping) or not isinstance(supplied, str):
            raise ValueError("payload and payload_hash are required")
        expected = canonical_json_sha256(payload)
        if not hmac.compare_digest(expected, supplied):
            raise ValueError("payload_hash does not match canonical payload bytes")
        return value


class CaptureCurrentRequest(NativeRequestBase):
    action: Literal[NativeAction.CAPTURE_CURRENT]
    payload: CaptureCurrentPayload


class StartSyncRequest(NativeRequestBase):
    action: Literal[NativeAction.START_SYNC]
    payload: StartSyncPayload


class GetJobRequest(NativeRequestBase):
    action: Literal[NativeAction.GET_JOB]
    payload: JobPayload


class CancelJobRequest(NativeRequestBase):
    action: Literal[NativeAction.CANCEL_JOB]
    payload: JobPayload


class RetryJobRequest(NativeRequestBase):
    action: Literal[NativeAction.RETRY_JOB]
    payload: JobPayload


class GetCapabilitiesRequest(NativeRequestBase):
    action: Literal[NativeAction.GET_CAPABILITIES]
    payload: EmptyPayload


class HealthRequest(NativeRequestBase):
    action: Literal[NativeAction.HEALTH]
    payload: EmptyPayload


NativeRequestUnion = Annotated[
    Union[
        CaptureCurrentRequest,
        StartSyncRequest,
        GetJobRequest,
        CancelJobRequest,
        RetryJobRequest,
        GetCapabilitiesRequest,
        HealthRequest,
    ],
    Field(discriminator="action"),
]


class NativeMessageRequest(RootModel[NativeRequestUnion]):
    model_config = ConfigDict(strict=True)


class NativeResponseStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    REJECTED = "rejected"


class NativeMessageResponse(StrictContract):
    schema_version: SchemaVersion
    request_id: UUID
    accepted: bool
    job_id: UUID | None = None
    status: NativeResponseStatus
    error: ErrorContract | None = None

    @model_validator(mode="after")
    def accepted_and_error_are_consistent(self) -> "NativeMessageResponse":
        if self.accepted and self.error is not None:
            raise ValueError("accepted response cannot contain an error")
        if not self.accepted and (self.error is None or self.status is not NativeResponseStatus.REJECTED):
            raise ValueError("rejected response requires a stable error")
        if self.status in {NativeResponseStatus.QUEUED, NativeResponseStatus.RUNNING} and self.job_id is None:
            raise ValueError("job status requires job_id")
        return self


class NativeHostPolicy(StrictContract):
    schema_version: SchemaVersion
    policy_id: Literal["NATIVE_HOST.X2N.001"]
    allowed_origins: Annotated[tuple[str, ...], Field(min_length=1, max_length=4)]
    allowed_actions: Annotated[tuple[NativeAction, ...], Field(min_length=7, max_length=7)]
    max_message_bytes: Annotated[int, Field(ge=1_024, le=1_048_576)]
    request_id_window_seconds: Literal[86_400]
    duplicate_policy: Literal["return_existing_job_only"]
    unknown_fields: Literal["reject"]
    unknown_versions: Literal["reject"]
    arbitrary_shell: Literal["reject"]
    arbitrary_local_path: Literal["reject"]
    arbitrary_url: Literal["reject"]

    @model_validator(mode="after")
    def origin_and_action_allowlists_are_exact(self) -> "NativeHostPolicy":
        origin_pattern = re.compile(r"^chrome-extension://[a-p]{32}/$")
        if len(set(self.allowed_origins)) != len(self.allowed_origins):
            raise ValueError("allowed_origins must be unique")
        if any("*" in origin or origin_pattern.fullmatch(origin) is None for origin in self.allowed_origins):
            raise ValueError("allowed_origins must contain exact extension origins without wildcards")
        if self.allowed_actions != tuple(NativeAction):
            raise ValueError("allowed_actions must equal the version 1.0 action registry")
        return self


class ContractViolation(ValueError):
    """Safe parse failure carrying a stable public error code only."""

    def __init__(self, code: ErrorCode, safe_message: str) -> None:
        self.code = code
        super().__init__(safe_message)


_FORBIDDEN_MESSAGE_KEYS = {
    "argv",
    "authorization",
    "command",
    "cookie",
    "cookies",
    "download_url",
    "executable",
    "file_path",
    "headers",
    "local_path",
    "media_url",
    "path",
    "proxy_url",
    "shell",
    "token",
}


def _validate_message_key_surface(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).lower()
            if normalized in _FORBIDDEN_MESSAGE_KEYS:
                raise ContractViolation(ErrorCode.SECURITY_INJECTION_BLOCKED, "危险输入字段已阻断")
            if normalized.endswith("_url") and normalized != "page_url":
                raise ContractViolation(ErrorCode.URL_REJECTED, "任意 URL 输入已阻断")
            _validate_message_key_surface(item)
    elif isinstance(value, list):
        for item in value:
            _validate_message_key_surface(item)


def parse_native_message(raw: bytes | str, *, origin: str, policy: NativeHostPolicy) -> NativeRequestUnion:
    """Validate a Native Messaging request without dispatching or side effects."""

    raw_bytes = raw.encode("utf-8") if isinstance(raw, str) else raw
    if origin not in policy.allowed_origins:
        raise ContractViolation(ErrorCode.NATIVE_ORIGIN_REJECTED, "调用来源未获允许")
    if len(raw_bytes) > policy.max_message_bytes:
        raise ContractViolation(ErrorCode.NATIVE_MESSAGE_TOO_LARGE, "消息超过允许大小")
    try:
        decoded = raw_bytes.decode("utf-8")
        payload = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContractViolation(ErrorCode.UNKNOWN_FIELD, "消息不是有效 JSON 对象") from error
    if not isinstance(payload, dict):
        raise ContractViolation(ErrorCode.UNKNOWN_FIELD, "消息必须是 JSON 对象")
    if payload.get("schema_version") != CONTRACT_VERSION:
        raise ContractViolation(ErrorCode.INVALID_SCHEMA_VERSION, "消息版本不受支持")
    if payload.get("action") not in {item.value for item in policy.allowed_actions}:
        raise ContractViolation(ErrorCode.NATIVE_ACTION_UNKNOWN, "消息动作不受支持")
    _validate_message_key_surface(payload)
    if payload.get("action") == NativeAction.CAPTURE_CURRENT.value:
        action_payload = payload.get("payload")
        if isinstance(action_payload, Mapping):
            platform = action_payload.get("platform")
            page_url = action_payload.get("page_url")
            if isinstance(platform, str) and isinstance(page_url, str):
                try:
                    validate_canonical_page_url(page_url, platform)
                except ValueError as error:
                    raise ContractViolation(ErrorCode.URL_REJECTED, "规范页面地址未通过允许列表") from error
    try:
        request = NativeMessageRequest.model_validate_json(decoded).root
    except ValidationError as error:
        code = ErrorCode.UNKNOWN_FIELD if any(item.get("type") == "extra_forbidden" for item in error.errors()) else ErrorCode.INVALID_INPUT
        raise ContractViolation(code, "消息未通过严格 Schema") from error
    return request


def classify_duplicate_request(previous_payload_hash: str | None, request: NativeRequestUnion) -> DuplicateDisposition:
    """Return the required ledger disposition; this function does not create a Job."""

    if previous_payload_hash is None:
        return DuplicateDisposition.NEW_REQUEST
    if hmac.compare_digest(previous_payload_hash, request.payload_hash):
        return DuplicateDisposition.RETURN_EXISTING_JOB
    return DuplicateDisposition.REJECT_CONFLICT


class CanonicalContent(StrictContract):
    schema_version: SchemaVersion
    content_key: ContractKey
    platform: Platform
    platform_content_id: PlatformContentId
    canonical_source_url: Annotated[str, StringConstraints(min_length=9, max_length=2_048)]
    content_type: ContentType
    title: Annotated[str, StringConstraints(max_length=500)] | None = None
    description: Annotated[str, StringConstraints(max_length=20_000)] | None = None
    author_name: Annotated[str, StringConstraints(max_length=500)] | None = None
    author_platform_id: PlatformContentId | None = None
    published_at: RFC3339DateTime | None = None
    content_hash: Sha256
    first_observed_at: RFC3339DateTime
    last_observed_at: RFC3339DateTime
    record_version: Annotated[int, Field(ge=1)]
    status: ContentStatus

    @model_validator(mode="after")
    def canonical_identity_matches(self) -> "CanonicalContent":
        if self.content_key != build_content_key(self.platform, self.platform_content_id):
            raise ValueError("content_key does not match platform and platform_content_id")
        validate_canonical_page_url(self.canonical_source_url, self.platform)
        if self.first_observed_at > self.last_observed_at:
            raise ValueError("observation time range is reversed")
        return self


class UserRelation(StrictContract):
    schema_version: SchemaVersion
    relation_key: ContractKey
    account_ref_hash: Sha256
    content_key: ContractKey
    relation_type: RelationType
    source_collection_id: SafeToken | None = None
    source_collection_name_private: Annotated[str, StringConstraints(max_length=500)] | None = None
    first_seen_at: RFC3339DateTime
    last_seen_at: RFC3339DateTime
    status: RelationStatus
    confirmed_by: ConfirmationSource
    scan_receipt_id: OpaqueRef

    @model_validator(mode="after")
    def relation_identity_matches(self) -> "UserRelation":
        expected = build_relation_key(
            self.account_ref_hash,
            self.content_key,
            self.relation_type,
            self.source_collection_id,
        )
        if self.relation_key != expected:
            raise ValueError("relation_key does not match relation identity")
        if self.first_seen_at > self.last_seen_at:
            raise ValueError("relation time range is reversed")
        if self.source_collection_name_private is not None and self.source_collection_id is None:
            raise ValueError("collection name requires collection id")
        return self


class SourceMethod(str, Enum):
    CURRENT_PAGE = "current_page"
    SELECTED_COLLECTION = "selected_collection"
    ADAPTER_SUPPLEMENT = "adapter_supplement"


class CanonicalField(str, Enum):
    PLATFORM_CONTENT_ID = "platform_content_id"
    CANONICAL_SOURCE_URL = "canonical_source_url"
    CONTENT_TYPE = "content_type"
    TITLE = "title"
    DESCRIPTION = "description"
    AUTHOR_NAME = "author_name"
    AUTHOR_PLATFORM_ID = "author_platform_id"
    PUBLISHED_AT = "published_at"


class FieldSource(str, Enum):
    DOM = "dom"
    ADAPTER = "adapter"
    OWNER = "owner"
    DERIVED = "derived"


class FieldStatus(str, Enum):
    PRESENT = "present"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class FieldProvenance(StrictContract):
    field: CanonicalField
    source: FieldSource
    status: FieldStatus
    confidence: Annotated[float, Field(ge=0, le=1)] | None = None


class SourceObservation(StrictContract):
    schema_version: SchemaVersion
    observation_id: OpaqueRef
    content_key: ContractKey
    adapter_name: SafeToken
    adapter_version: SafeToken
    source_method: SourceMethod
    observed_at: RFC3339DateTime
    raw_text_hash: Sha256
    normalized_fields: Annotated[tuple[CanonicalField, ...], Field(min_length=1)]
    field_provenance: Annotated[tuple[FieldProvenance, ...], Field(min_length=1)]
    completeness: Annotated[float, Field(ge=0, le=1)]
    warning_codes: tuple[ErrorCode, ...] = ()
    ephemeral_media_ref_ids: tuple[OpaqueRef, ...] = ()
    run_id: OpaqueRef

    @model_validator(mode="after")
    def observation_sets_are_consistent(self) -> "SourceObservation":
        if len(set(self.normalized_fields)) != len(self.normalized_fields):
            raise ValueError("normalized_fields contains duplicates")
        provenance_fields = [item.field for item in self.field_provenance]
        if len(set(provenance_fields)) != len(provenance_fields):
            raise ValueError("field_provenance contains duplicates")
        if set(provenance_fields) != set(self.normalized_fields):
            raise ValueError("field_provenance must cover normalized_fields exactly")
        if len(set(self.ephemeral_media_ref_ids)) != len(self.ephemeral_media_ref_ids):
            raise ValueError("ephemeral media refs must be unique")
        return self


class QualityGrade(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class ArtifactQuality(StrictContract):
    grade: QualityGrade
    metric_name: SafeToken | None = None
    metric_value: Annotated[float, Field(ge=0)] | None = None

    @model_validator(mode="after")
    def metric_pair_is_complete(self) -> "ArtifactQuality":
        if (self.metric_name is None) != (self.metric_value is None):
            raise ValueError("quality metric name and value must appear together")
        return self


class Artifact(StrictContract):
    schema_version: SchemaVersion
    artifact_id: OpaqueRef
    artifact_key: ContractKey
    content_key: ContractKey
    artifact_type: ArtifactType
    input_hash: Sha256
    processor: SafeToken
    processor_version: SafeToken
    model_provider: SafeToken | None = None
    model_name: SafeToken | None = None
    model_snapshot: SafeToken | None = None
    prompt_version: SafeToken | None = None
    language: SafeToken | None = None
    quality: ArtifactQuality
    private_payload_present: bool
    private_payload_ref: OpaqueRef | None = None
    private_payload_hash: Sha256 | None = None
    append_only: Literal[True]
    artifact_sequence: Annotated[int, Field(ge=1)]
    created_at: RFC3339DateTime
    supersedes_artifact_id: OpaqueRef | None = None

    @model_validator(mode="after")
    def artifact_identity_and_payload_match(self) -> "Artifact":
        expected = build_artifact_key(
            self.content_key,
            self.artifact_type,
            self.input_hash,
            self.processor_version,
        )
        if self.artifact_key != expected:
            raise ValueError("artifact_key does not match immutable inputs")
        payload_refs_present = self.private_payload_ref is not None and self.private_payload_hash is not None
        if self.private_payload_present != payload_refs_present:
            raise ValueError("private payload flag/ref/hash are inconsistent")
        if self.supersedes_artifact_id == self.artifact_id:
            raise ValueError("artifact cannot supersede itself")
        model_fields = (self.model_provider, self.model_name, self.model_snapshot)
        if any(item is not None for item in model_fields) and not all(item is not None for item in model_fields):
            raise ValueError("model provider/name/snapshot must appear together")
        return self


class TaxonomyCategory(StrictContract):
    schema_version: SchemaVersion
    category_id: UUID
    name: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    slug: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,62}$")]
    description: Annotated[str, StringConstraints(min_length=1, max_length=2_000)]
    aliases: tuple[Annotated[str, StringConstraints(min_length=1, max_length=100)], ...] = ()
    positive_examples: tuple[PrivateText, ...] = ()
    negative_examples: tuple[PrivateText, ...] = ()
    priority: int
    enabled: bool
    version: Annotated[int, Field(ge=1)]
    level: Literal[1]
    created_by: Literal["owner"]

    @model_validator(mode="after")
    def category_terms_are_unique(self) -> "TaxonomyCategory":
        normalized = [self.name.casefold(), *(item.casefold() for item in self.aliases)]
        if len(set(normalized)) != len(normalized):
            raise ValueError("category name and aliases must be unique")
        return self


class DecisionMode(str, Enum):
    RULE = "rule"
    MODEL = "model"
    HYBRID = "hybrid"
    HUMAN = "human"


class ReviewStatus(str, Enum):
    AUTO_ACCEPTED = "auto_accepted"
    SUGGESTED = "suggested"
    OWNER_CONFIRMED = "owner_confirmed"
    OWNER_CORRECTED = "owner_corrected"


class ClassificationCandidate(StrictContract):
    category_id: UUID
    calibrated_score: Annotated[float, Field(ge=0, le=1)]


class Classification(StrictContract):
    schema_version: SchemaVersion
    classification_id: OpaqueRef
    content_key: ContractKey
    taxonomy_version: Annotated[int, Field(ge=1)]
    primary_category_id: UUID
    tags: tuple[Annotated[str, StringConstraints(min_length=1, max_length=100)], ...] = ()
    candidate_ranking: Annotated[tuple[ClassificationCandidate, ...], Field(max_length=20)] = ()
    decision_mode: DecisionMode
    confidence_raw: Annotated[float, Field(ge=0, le=1)] | None = None
    calibration_bucket: SafeToken | None = None
    evidence_artifact_ids: Annotated[tuple[OpaqueRef, ...], Field(min_length=1)]
    explanation_private_ref: OpaqueRef | None = None
    review_status: ReviewStatus
    created_at: RFC3339DateTime
    supersedes_classification_id: OpaqueRef | None = None

    @model_validator(mode="after")
    def ranking_is_deterministic(self) -> "Classification":
        ids = [item.category_id for item in self.candidate_ranking]
        if len(set(ids)) != len(ids):
            raise ValueError("candidate category ids must be unique")
        scores = [item.calibrated_score for item in self.candidate_ranking]
        if scores != sorted(scores, reverse=True):
            raise ValueError("candidate ranking must be descending")
        if ids and self.primary_category_id not in ids:
            raise ValueError("primary category must appear in candidate ranking")
        if len(set(self.evidence_artifact_ids)) != len(self.evidence_artifact_ids):
            raise ValueError("evidence artifact ids must be unique")
        if self.supersedes_classification_id == self.classification_id:
            raise ValueError("classification cannot supersede itself")
        return self


class SinkReceiptStatus(str, Enum):
    DELIVERED = "delivered"
    VERIFIED = "verified"
    FAILED = "failed"


class SinkReceipt(StrictContract):
    schema_version: SchemaVersion
    receipt_id: OpaqueRef
    sink_key: ContractKey
    sink: SinkKind
    content_key: ContractKey
    sink_schema_version: SafeToken
    desired_projection_hash: Sha256
    output_hash: Sha256
    sink_object_ref: OpaqueRef
    external_ref_hash: Sha256 | None = None
    status: SinkReceiptStatus
    delivered_at: RFC3339DateTime
    run_id: OpaqueRef

    @model_validator(mode="after")
    def sink_identity_matches(self) -> "SinkReceipt":
        if self.sink_key != build_sink_key(self.sink, self.content_key, self.sink_schema_version):
            raise ValueError("sink_key does not match sink identity")
        if self.sink is SinkKind.NOTION and self.external_ref_hash is None:
            raise ValueError("Notion receipt requires a hashed external reference")
        if self.sink is SinkKind.MARKDOWN and self.external_ref_hash is not None:
            raise ValueError("Markdown receipt cannot contain an external reference")
        return self


class HealthComponentName(str, Enum):
    EXTENSION = "extension"
    NATIVE_HOST = "native_host"
    COMPANION = "companion"
    CANONICAL_DB = "canonical_db"
    FFMPEG = "ffmpeg"
    PROVIDER = "provider"
    NOTION = "notion"
    ADAPTER = "adapter"


class HealthState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class HealthComponent(StrictContract):
    component: HealthComponentName
    state: HealthState
    observed_at: RFC3339DateTime
    error: ErrorContract | None = None

    @model_validator(mode="after")
    def error_matches_state(self) -> "HealthComponent":
        if self.state is HealthState.HEALTHY and self.error is not None:
            raise ValueError("healthy component cannot contain an error")
        if self.state is not HealthState.HEALTHY and self.error is None:
            raise ValueError("non-healthy component requires a stable error")
        return self


class HealthReport(StrictContract):
    schema_version: SchemaVersion
    report_id: OpaqueRef
    observed_at: RFC3339DateTime
    overall: HealthState
    components: Annotated[tuple[HealthComponent, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def overall_matches_components(self) -> "HealthReport":
        names = [item.component for item in self.components]
        if len(set(names)) != len(names):
            raise ValueError("health components must be unique")
        states = {item.state for item in self.components}
        expected = (
            HealthState.FAILED
            if HealthState.FAILED in states
            else HealthState.DEGRADED
            if states != {HealthState.HEALTHY}
            else HealthState.HEALTHY
        )
        if self.overall is not expected:
            raise ValueError("overall health does not match component states")
        return self


class ProvenanceNodeKind(str, Enum):
    CANONICAL = "canonical"
    SOURCE_OBSERVATION = "source_observation"
    ADAPTER = "adapter"
    ARTIFACT = "artifact"
    CLASSIFICATION = "classification"
    RUN = "run"
    RENDERER = "renderer"
    SINK_RECEIPT = "sink_receipt"


class ProvenanceNode(StrictContract):
    node_id: Annotated[str, StringConstraints(pattern=r"^node_[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")]
    kind: ProvenanceNodeKind
    reference: Annotated[str, StringConstraints(min_length=1, max_length=768)]
    version: SafeToken
    evidence_hash: Sha256


class ProvenanceRelation(str, Enum):
    TRACES_TO = "traces_to"


class ProvenanceEdge(StrictContract):
    from_node_id: Annotated[str, StringConstraints(pattern=r"^node_[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")]
    to_node_id: Annotated[str, StringConstraints(pattern=r"^node_[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")]
    relation: Literal[ProvenanceRelation.TRACES_TO]


class ProvenanceChain(StrictContract):
    schema_version: SchemaVersion
    chain_id: OpaqueRef
    content_key: ContractKey
    output_kind: SinkKind
    output_node_id: Annotated[str, StringConstraints(pattern=r"^node_[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")]
    nodes: Annotated[tuple[ProvenanceNode, ...], Field(min_length=7)]
    edges: Annotated[tuple[ProvenanceEdge, ...], Field(min_length=6)]
    completeness_percent: Literal[100]

    @model_validator(mode="after")
    def required_graph_is_connected(self) -> "ProvenanceChain":
        node_by_id = {item.node_id: item for item in self.nodes}
        if len(node_by_id) != len(self.nodes):
            raise ValueError("provenance node ids must be unique")
        if self.output_node_id not in node_by_id:
            raise ValueError("output node is missing")
        expected_output_kind = (
            ProvenanceNodeKind.SINK_RECEIPT if self.output_kind is SinkKind.NOTION else ProvenanceNodeKind.RENDERER
        )
        if node_by_id[self.output_node_id].kind is not expected_output_kind:
            raise ValueError("output node kind does not match sink")
        required = {
            ProvenanceNodeKind.CANONICAL,
            ProvenanceNodeKind.SOURCE_OBSERVATION,
            ProvenanceNodeKind.ADAPTER,
            ProvenanceNodeKind.ARTIFACT,
            ProvenanceNodeKind.CLASSIFICATION,
            ProvenanceNodeKind.RUN,
            ProvenanceNodeKind.RENDERER,
        }
        if self.output_kind is SinkKind.NOTION:
            required.add(ProvenanceNodeKind.SINK_RECEIPT)
        present = {item.kind for item in self.nodes}
        if not required.issubset(present):
            raise ValueError("required provenance node kind is missing")
        adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_by_id}
        seen_edges: set[tuple[str, str]] = set()
        for edge in self.edges:
            key = (edge.from_node_id, edge.to_node_id)
            if edge.from_node_id not in node_by_id or edge.to_node_id not in node_by_id:
                raise ValueError("provenance edge references an unknown node")
            if edge.from_node_id == edge.to_node_id or key in seen_edges:
                raise ValueError("provenance edge is self-referential or duplicated")
            seen_edges.add(key)
            adjacency[edge.from_node_id].append(edge.to_node_id)
        reachable: set[str] = set()
        queue: deque[str] = deque([self.output_node_id])
        while queue:
            current = queue.popleft()
            if current in reachable:
                continue
            reachable.add(current)
            queue.extend(adjacency[current])
        required_node_ids = {item.node_id for item in self.nodes if item.kind in required}
        if not required_node_ids.issubset(reachable):
            raise ValueError("final output cannot trace to every required provenance node")
        return self


class CompatibilityPolicy(StrictContract):
    schema_version: SchemaVersion
    contract_version: SchemaVersion
    accepted_read_versions: tuple[SchemaVersion, ...]
    compatibility_mode: Literal["exact_match_fail_closed"]
    unknown_fields: Literal["reject"]
    unknown_versions: Literal["reject"]
    destructive_migration: Literal["forbidden_without_versioned_migration"]

    @model_validator(mode="after")
    def accepted_versions_are_exact(self) -> "CompatibilityPolicy":
        if self.accepted_read_versions != (CONTRACT_VERSION,):
            raise ValueError("version 1.0 accepts only exact version 1.0")
        return self


SCHEMA_MODELS: dict[str, type[RootModel[Any]] | type[StrictContract]] = {
    "native_message_request": NativeMessageRequest,
    "native_message_response": NativeMessageResponse,
    "native_host_policy": NativeHostPolicy,
    "canonical_content": CanonicalContent,
    "user_relation": UserRelation,
    "source_observation": SourceObservation,
    "artifact": Artifact,
    "taxonomy_category": TaxonomyCategory,
    "classification": Classification,
    "sink_receipt": SinkReceipt,
    "health_report": HealthReport,
    "error": ErrorContract,
    "provenance_chain": ProvenanceChain,
    "compatibility_policy": CompatibilityPolicy,
}
