"""Fail-closed Taobao owner-selected item hydration contract.

The module has no network transport, OAuth client, browser automation, Cookie,
MTop signing, proxy, or automatic retry. It accepts only a credential-free
manifest for item IDs the Owner explicitly selected and a minimal sanitized
``taobao.item.get`` result shape (``num_iid`` and ``title``). It never claims
that Taobao exposed a personal favorites-list API. Production requests stay
disabled until application, scope, price, quota, retention, deletion, official
transport, local-only storage, and route gates are independently attested.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime
from typing import Any, Literal

from x2n_contracts import CanonicalContent, ErrorCode, SourceObservation, UserRelation, build_content_key
from x2n_contracts.models import (
    CanonicalField,
    ConfirmationSource,
    ContentStatus,
    ContentType,
    FieldProvenance,
    FieldSource,
    FieldStatus,
    Platform,
    RelationStatus,
    RelationType,
    SourceMethod,
    build_relation_key,
)

from .adapter_guard import AdapterExecutionGate
from .canonical_store import CanonicalStore, WriteDisposition
from .runtime import X2NRuntimeError


TASK_ID = "TSK.x2n.adapters.009"
ADAPTER_NAME = "taobao_selected_collection"
ADAPTER_VERSION = "1.0.0"
RESUME_COMPATIBILITY_VERSION = "taobao-selected-1.0.0"
RUN_KIND = "taobao_owner_selection_v1"
POLICY_REVISION = "2026-07-23"
SOURCE_KIND = "owner_explicit_item_ids_for_authorized_item_get"
CANARY_ITEM_LIMIT = 20
PRODUCTION_ENABLED = False

SHA256 = re.compile(r"^[0-9a-f]{64}$")
NUM_IID = re.compile(r"^[1-9][0-9]{5,20}$")
SELECTION_ID = re.compile(r"^x2nsel_[0-9a-f]{32}$")
SYNTHETIC_ITEM_PREFIX = "9900000000000"
MAX_RETRY_AFTER_SECONDS = 2_592_000
BatchStatus = Literal[
    "ready",
    "partial",
    "auth_required",
    "oauth_revoked",
    "budget_blocked",
    "retention_blocked",
    "rate_limited",
    "policy_blocked",
    "empty_unverified",
    "platform_changed",
]
FaultInjector = Callable[[str], None]


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Taobao time requires an explicit timezone")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _timestamp(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.endswith("Z"):
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Taobao published time is invalid")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Taobao published time is invalid") from None
    if _timestamp(parsed) != value:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Taobao published time is not canonical")
    return parsed


def _retry_not_before(value: Any, received_at: datetime) -> tuple[int, datetime]:
    """Normalize RFC Retry-After without sleeping or issuing another request."""

    if not isinstance(value, str) or not value or len(value) > 64 or re.search(r"[^\x20-\x7e]", value):
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Taobao Retry-After is invalid")
    received = _utc(received_at)
    if value.isdigit():
        seconds = int(value)
        if seconds > MAX_RETRY_AFTER_SECONDS:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Taobao Retry-After exceeds the bounded hold")
        return seconds, received + timedelta(seconds=seconds)
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Taobao Retry-After is invalid") from None
    if parsed.tzinfo is None or format_datetime(parsed.astimezone(timezone.utc), usegmt=True) != value:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Taobao Retry-After date is not canonical")
    target = _utc(parsed)
    seconds = int((target - received).total_seconds())
    if seconds < 0 or seconds > MAX_RETRY_AFTER_SECONDS:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Taobao Retry-After date is outside the bounded hold")
    return seconds, target


def _safe_title(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 500
        or value != " ".join(value.split())
        or re.search(r"[\x00-\x1f\x7f]", value)
        or re.search(r"https?://", value, flags=re.IGNORECASE)
    ):
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Taobao title is unsafe")
    return value


def _scan_uuid(value: str) -> uuid.UUID:
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, TypeError, ValueError):
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Taobao scan identity is invalid") from None
    if str(parsed) != value:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Taobao scan identity is not canonical")
    return parsed


def _identity(scan_id: str) -> dict[str, str]:
    suffix = _scan_uuid(scan_id).hex
    return {
        "checkpoint_id": f"checkpoint_tbsel_{suffix}",
        "run_id": f"run_tbsel_{suffix}",
        "scan_receipt_id": f"receipt_tbsel_{suffix}",
    }


def _canonical_page_url() -> str:
    return "https://item.taobao.com/item.htm"


@dataclass(frozen=True)
class TaobaoCapabilityReceipt:
    """Credential-free App/OAuth/budget/retention attestation."""

    environment: Literal["ci_synthetic", "owner_runtime"]
    source_kind: Literal["owner_explicit_item_ids_for_authorized_item_get"]
    policy_revision: Literal["2026-07-23"]
    authorization_ref_sha256: str
    pricing_ref_sha256: str
    quota_ref_sha256: str
    retention_ref_sha256: str
    application_approved: bool
    owner_oauth_active: bool
    item_get_scope_granted: bool
    pricing_confirmed: bool
    quota_confirmed: bool
    approved_budget_units: int
    projected_cost_units: int | None
    remaining_quota_requests: int | None
    official_top_transport_attested: bool
    sanitized_transport_attested: bool
    local_only_storage_attested: bool
    canonical_route_attested: bool
    purpose_scope_disclosure_approved: bool
    retention_period_approved: bool
    delete_revoke_flow_ready: bool
    deletion_receipt_ready: bool
    authorization_revoked: bool
    credential_material_present: Literal[False] = False

    def __post_init__(self) -> None:
        if self.environment not in {"ci_synthetic", "owner_runtime"}:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Taobao capability environment is invalid")
        if self.source_kind != SOURCE_KIND or self.policy_revision != POLICY_REVISION:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Taobao capability policy is stale")
        for label, value in (
            ("authorization", self.authorization_ref_sha256),
            ("pricing", self.pricing_ref_sha256),
            ("quota", self.quota_ref_sha256),
            ("retention", self.retention_ref_sha256),
        ):
            if not isinstance(value, str) or SHA256.fullmatch(value) is None:
                raise X2NRuntimeError(ErrorCode.INVALID_INPUT, f"Taobao {label} reference is invalid")
        flags = (
            self.application_approved,
            self.owner_oauth_active,
            self.item_get_scope_granted,
            self.pricing_confirmed,
            self.quota_confirmed,
            self.official_top_transport_attested,
            self.sanitized_transport_attested,
            self.local_only_storage_attested,
            self.canonical_route_attested,
            self.purpose_scope_disclosure_approved,
            self.retention_period_approved,
            self.delete_revoke_flow_ready,
            self.deletion_receipt_ready,
            self.authorization_revoked,
            self.credential_material_present,
        )
        if any(type(flag) is not bool for flag in flags) or self.credential_material_present is not False:
            raise X2NRuntimeError(ErrorCode.SECURITY_INJECTION_BLOCKED, "Taobao capability flags are invalid")
        for label, value in (
            ("approved budget", self.approved_budget_units),
            ("projected cost", self.projected_cost_units),
            ("remaining quota", self.remaining_quota_requests),
        ):
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                raise X2NRuntimeError(ErrorCode.INVALID_INPUT, f"Taobao {label} is invalid")
        if self.environment == "ci_synthetic" and (
            any(flags[:-1])
            or self.approved_budget_units != 0
            or self.projected_cost_units is not None
            or self.remaining_quota_requests is not None
        ):
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Synthetic capability cannot claim real authorization")
        if self.authorization_revoked and self.owner_oauth_active:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Revoked Taobao OAuth cannot remain active")
        if self.pricing_confirmed != (self.projected_cost_units is not None):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Taobao pricing receipt is incomplete")
        if self.quota_confirmed != (self.remaining_quota_requests is not None):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Taobao quota receipt is incomplete")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "TaobaoCapabilityReceipt":
        expected = {
            "approved_budget_units",
            "application_approved",
            "authorization_revoked",
            "authorization_ref_sha256",
            "canonical_route_attested",
            "credential_material_present",
            "environment",
            "item_get_scope_granted",
            "local_only_storage_attested",
            "owner_oauth_active",
            "policy_revision",
            "pricing_confirmed",
            "pricing_ref_sha256",
            "projected_cost_units",
            "quota_confirmed",
            "quota_ref_sha256",
            "retention_ref_sha256",
            "remaining_quota_requests",
            "official_top_transport_attested",
            "sanitized_transport_attested",
            "source_kind",
            "purpose_scope_disclosure_approved",
            "retention_period_approved",
            "delete_revoke_flow_ready",
            "deletion_receipt_ready",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise X2NRuntimeError(ErrorCode.UNKNOWN_FIELD, "Taobao capability shape is invalid")
        return cls(**dict(value))  # type: ignore[arg-type]

    def receipt_hash(self) -> str:
        return _sha256(
            {
                "approved_budget_units": self.approved_budget_units,
                "application_approved": self.application_approved,
                "authorization_revoked": self.authorization_revoked,
                "authorization_ref_sha256": self.authorization_ref_sha256,
                "canonical_route_attested": self.canonical_route_attested,
                "credential_material_present": self.credential_material_present,
                "environment": self.environment,
                "item_get_scope_granted": self.item_get_scope_granted,
                "local_only_storage_attested": self.local_only_storage_attested,
                "owner_oauth_active": self.owner_oauth_active,
                "policy_revision": self.policy_revision,
                "pricing_confirmed": self.pricing_confirmed,
                "pricing_ref_sha256": self.pricing_ref_sha256,
                "projected_cost_units": self.projected_cost_units,
                "quota_confirmed": self.quota_confirmed,
                "quota_ref_sha256": self.quota_ref_sha256,
                "retention_ref_sha256": self.retention_ref_sha256,
                "remaining_quota_requests": self.remaining_quota_requests,
                "official_top_transport_attested": self.official_top_transport_attested,
                "sanitized_transport_attested": self.sanitized_transport_attested,
                "source_kind": self.source_kind,
                "purpose_scope_disclosure_approved": self.purpose_scope_disclosure_approved,
                "retention_period_approved": self.retention_period_approved,
                "delete_revoke_flow_ready": self.delete_revoke_flow_ready,
                "deletion_receipt_ready": self.deletion_receipt_ready,
            }
        )


@dataclass(frozen=True)
class TaobaoCapabilityDecision:
    status: str
    offline_mapping_permitted: bool
    platform_requests_permitted: bool
    missing_requirements: tuple[str, ...]
    authorization_cleanup_required: bool
    approved_budget_units: int
    projected_cost_units: int | None
    remaining_quota_requests: int | None

    def safe_dict(self) -> dict[str, Any]:
        return {
            "approved_budget_units": self.approved_budget_units,
            "authorization_cleanup_required": self.authorization_cleanup_required,
            "missing_requirements": list(self.missing_requirements),
            "offline_mapping_permitted": self.offline_mapping_permitted,
            "platform_requests_permitted": self.platform_requests_permitted,
            "production_enabled": PRODUCTION_ENABLED,
            "projected_cost_units": self.projected_cost_units,
            "remaining_quota_requests": self.remaining_quota_requests,
            "status": self.status,
        }


def evaluate_taobao_capability(receipt: TaobaoCapabilityReceipt) -> TaobaoCapabilityDecision:
    if receipt.environment == "ci_synthetic":
        return TaobaoCapabilityDecision("PASS_CI_SYNTHETIC", True, False, (), False, 0, None, None)
    values = (
        receipt.approved_budget_units,
        receipt.projected_cost_units,
        receipt.remaining_quota_requests,
    )
    if receipt.authorization_revoked:
        return TaobaoCapabilityDecision(
            "BLOCKED_AUTHORIZATION_REVOKED",
            False,
            False,
            ("owner_oauth_active",),
            True,
            *values,
        )
    if receipt.approved_budget_units == 0:
        return TaobaoCapabilityDecision("BLOCKED_BUDGET_ZERO", False, False, ("nonzero_owner_budget",), False, *values)
    if not receipt.pricing_confirmed or not receipt.quota_confirmed:
        return TaobaoCapabilityDecision(
            "BLOCKED_PRICE_OR_QUOTA_UNKNOWN",
            False,
            False,
            ("pricing_snapshot", "quota_snapshot"),
            False,
            *values,
        )
    assert receipt.projected_cost_units is not None and receipt.remaining_quota_requests is not None
    if receipt.projected_cost_units > receipt.approved_budget_units:
        return TaobaoCapabilityDecision("BLOCKED_BUDGET_EXCEEDED", False, False, ("approved_budget",), False, *values)
    if receipt.remaining_quota_requests < 1:
        return TaobaoCapabilityDecision("BLOCKED_QUOTA_EXHAUSTED", False, False, ("remaining_quota",), False, *values)
    retention_requirements = {
        "delete_revoke_flow": receipt.delete_revoke_flow_ready,
        "deletion_receipt": receipt.deletion_receipt_ready,
        "purpose_scope_disclosure": receipt.purpose_scope_disclosure_approved,
        "retention_period": receipt.retention_period_approved,
    }
    retention_missing = tuple(sorted(name for name, present in retention_requirements.items() if not present))
    if retention_missing:
        return TaobaoCapabilityDecision(
            "BLOCKED_RETENTION_UNKNOWN", False, False, retention_missing, False, *values
        )
    requirements = {
        "application_approval": receipt.application_approved,
        "canonical_route_attestation": receipt.canonical_route_attested,
        "item_get_scope": receipt.item_get_scope_granted,
        "local_only_storage_attestation": receipt.local_only_storage_attested,
        "official_top_transport": receipt.official_top_transport_attested,
        "owner_oauth": receipt.owner_oauth_active,
        "sanitized_transport": receipt.sanitized_transport_attested,
    }
    missing = tuple(sorted(name for name, present in requirements.items() if not present))
    if missing:
        return TaobaoCapabilityDecision("BLOCKED_MISSING_AUTHORIZATION", False, False, missing, False, *values)
    return TaobaoCapabilityDecision(
        "BLOCKED_FEATURE_DISABLED", False, False, ("production_feature_flag",), False, *values
    )


@dataclass(frozen=True)
class TaobaoSelectedItem:
    num_iid: str
    title: str

    def __post_init__(self) -> None:
        if not isinstance(self.num_iid, str) or NUM_IID.fullmatch(self.num_iid) is None:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Taobao num_iid is invalid")
        _safe_title(self.title)

    def facts(self) -> dict[str, Any]:
        return {
            "num_iid": self.num_iid,
            "canonical_page_url": _canonical_page_url(),
            "content_type": ContentType.UNKNOWN.value,
            "published_at": None,
            "title": self.title,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "TaobaoSelectedItem":
        expected = {"num_iid", "title"}
        if not isinstance(value, Mapping) or set(value) != expected:
            raise X2NRuntimeError(ErrorCode.UNKNOWN_FIELD, "Taobao item shape is invalid")
        item = cls(
            num_iid=value["num_iid"],
            title=value["title"],
        )
        return item


@dataclass(frozen=True)
class TaobaoSelectedBatch:
    sequence: int
    status: BatchStatus
    selected_manifest_count: int
    items: tuple[TaobaoSelectedItem, ...]
    error_codes: tuple[str, ...]
    observed_at: datetime
    owner_selection_id: str
    selection_manifest_sha256: str
    http_status: int | None
    retry_after: str | None
    source_kind: Literal["owner_explicit_item_ids_for_authorized_item_get"] = SOURCE_KIND
    explicit_owner_action: Literal[True] = True
    automatic_pagination: Literal[False] = False
    automatic_scroll: Literal[False] = False

    def __post_init__(self) -> None:
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence != 0:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Taobao selection permits exactly one bounded batch")
        if self.status not in {
            "ready",
            "partial",
            "auth_required",
            "oauth_revoked",
            "budget_blocked",
            "retention_blocked",
            "rate_limited",
            "policy_blocked",
            "empty_unverified",
            "platform_changed",
        }:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Taobao batch status is invalid")
        if self.source_kind != SOURCE_KIND:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Taobao source kind is unsupported")
        if (
            self.explicit_owner_action is not True
            or self.automatic_pagination is not False
            or self.automatic_scroll is not False
        ):
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Taobao batch requires one explicit no-pagination action")
        if not isinstance(self.owner_selection_id, str) or SELECTION_ID.fullmatch(self.owner_selection_id) is None:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Taobao owner selection identity is invalid")
        if (
            not isinstance(self.selection_manifest_sha256, str)
            or SHA256.fullmatch(self.selection_manifest_sha256) is None
        ):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Taobao selection manifest reference is invalid")
        if (
            not isinstance(self.selected_manifest_count, int)
            or isinstance(self.selected_manifest_count, bool)
            or not 0 <= self.selected_manifest_count <= CANARY_ITEM_LIMIT
            or len(self.items) > CANARY_ITEM_LIMIT
        ):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Taobao selection boundary is invalid")
        if len({item.num_iid for item in self.items}) != len(self.items):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Taobao selection contains duplicate items")
        allowed_errors = {item.value for item in ErrorCode}
        if any(code not in allowed_errors for code in self.error_codes):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Taobao error evidence is invalid")
        if self.http_status is not None and (
            not isinstance(self.http_status, int) or isinstance(self.http_status, bool)
        ):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Taobao HTTP status is invalid")
        if self.status == "ready":
            if (
                not self.items
                or self.error_codes
                or len(self.items) != self.selected_manifest_count
                or self.http_status is not None
                or self.retry_after is not None
            ):
                raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Taobao ready manifest is incomplete")
        elif self.status == "partial":
            if (
                not self.items
                or not self.error_codes
                or len(self.items) >= self.selected_manifest_count
                or len(self.items) + len(self.error_codes) != self.selected_manifest_count
                or self.http_status is not None
                or self.retry_after is not None
            ):
                raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Taobao partial manifest lacks evidence")
        elif self.status == "rate_limited":
            if (
                self.items
                or self.selected_manifest_count != 0
                or self.error_codes != (ErrorCode.RATE_LIMITED.value,)
                or self.http_status != 429
                or self.retry_after is None
            ):
                raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Taobao 429 manifest lacks Retry-After")
            _retry_not_before(self.retry_after, self.observed_at)
        elif (
            self.items
            or not self.error_codes
            or self.selected_manifest_count != 0
            or self.http_status is not None
            or self.retry_after is not None
        ):
            raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Taobao blocked manifest is inconsistent")
        _utc(self.observed_at)

    def batch_hash(self) -> str:
        return _sha256(
            {
                "automatic_pagination": self.automatic_pagination,
                "automatic_scroll": self.automatic_scroll,
                "error_codes": self.error_codes,
                "explicit_owner_action": self.explicit_owner_action,
                "items": [item.facts() for item in self.items],
                "http_status": self.http_status,
                "observed_at": _timestamp(self.observed_at),
                "owner_selection_id": self.owner_selection_id,
                "selected_manifest_count": self.selected_manifest_count,
                "selection_manifest_sha256": self.selection_manifest_sha256,
                "sequence": self.sequence,
                "source_kind": self.source_kind,
                "status": self.status,
                "retry_after": self.retry_after,
            }
        )


class TaobaoSelectedIterator:
    """Converts one sanitized owner action; it cannot fetch or request another page."""

    def __init__(self, capability: TaobaoCapabilityReceipt) -> None:
        self.capability = capability

    def one_explicit_batch(self, value: Mapping[str, Any], *, observed_at: datetime) -> TaobaoSelectedBatch:
        decision = evaluate_taobao_capability(self.capability)
        if not decision.offline_mapping_permitted:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Taobao selected collection is not authorized")
        expected = {
            "automatic_pagination",
            "automatic_scroll",
            "error_codes",
            "explicit_owner_action",
            "has_more",
            "http_status",
            "items",
            "owner_selection_id",
            "page_number",
            "page_size",
            "platform",
            "policy_revision",
            "retry_after",
            "schema_version",
            "selected_manifest_count",
            "selection_manifest_sha256",
            "source_kind",
            "status",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise X2NRuntimeError(ErrorCode.UNKNOWN_FIELD, "Taobao sanitized manifest shape is invalid")
        if (
            value.get("schema_version") != "1.0"
            or value.get("platform") != Platform.TAOBAO.value
            or value.get("policy_revision") != POLICY_REVISION
            or value.get("source_kind") != SOURCE_KIND
        ):
            raise X2NRuntimeError(ErrorCode.INVALID_SCHEMA_VERSION, "Taobao sanitized manifest identity is invalid")
        if (
            type(value.get("page_number")) is not int
            or value.get("page_number") != 1
            or type(value.get("page_size")) is not int
            or value.get("page_size") != CANARY_ITEM_LIMIT
            or type(value.get("has_more")) is not bool
        ):
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Taobao page contract is not bounded")
        items = value.get("items")
        errors = value.get("error_codes")
        if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Taobao item list is invalid")
        if not isinstance(errors, Sequence) or isinstance(errors, (str, bytes)):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Taobao error list is invalid")
        batch = TaobaoSelectedBatch(
            sequence=0,
            status=value["status"],
            selected_manifest_count=value["selected_manifest_count"],
            items=tuple(TaobaoSelectedItem.from_mapping(item) for item in items),
            error_codes=tuple(errors),
            observed_at=observed_at,
            owner_selection_id=value["owner_selection_id"],
            selection_manifest_sha256=value["selection_manifest_sha256"],
            http_status=value["http_status"],
            retry_after=value["retry_after"],
            source_kind=value["source_kind"],
            explicit_owner_action=value["explicit_owner_action"],
            automatic_pagination=value["automatic_pagination"],
            automatic_scroll=value["automatic_scroll"],
        )
        if self.capability.environment == "ci_synthetic" and any(
            not item.num_iid.startswith(SYNTHETIC_ITEM_PREFIX) for item in batch.items
        ):
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Synthetic Taobao mapping requires synthetic identities")
        return batch


@dataclass(frozen=True)
class TaobaoSelectedReceipt:
    scan_ref_sha256: str
    disposition: Literal["applied", "replayed"]
    checkpoint_state: Literal["active", "complete", "invalidated"]
    cursor_kind: str
    next_sequence: int
    manifest_items: int
    identified_items: int
    identified_percent: float
    relation_count: int
    observation_count: int
    error_evidence_count: int
    platform_killed: bool
    authorization_cleanup_required: bool
    rate_limited: bool
    retry_not_before: str | None
    retry_after_seconds: int | None
    approved_budget_units: int
    projected_cost_units: int | None
    remaining_quota_requests: int | None
    capability_receipt_sha256: str
    retention_receipt_sha256: str
    retention_policy_ready: bool
    deletion_receipt_ready: bool

    def safe_dict(self) -> dict[str, Any]:
        return {
            "adapter": {"name": ADAPTER_NAME, "version": ADAPTER_VERSION},
            "automatic_pagination": 0,
            "automatic_scroll": 0,
            "checkpoint": {
                "cursor_kind": self.cursor_kind,
                "next_sequence": self.next_sequence,
                "state": self.checkpoint_state,
            },
            "content_auto_deletes": 0,
            "cost": {
                "approved_budget_units": self.approved_budget_units,
                "capability_receipt_sha256": self.capability_receipt_sha256,
                "platform_requests": 0,
                "projected_cost_units": self.projected_cost_units,
                "remaining_quota_requests": self.remaining_quota_requests,
            },
            "disposition": self.disposition,
            "error_evidence_count": self.error_evidence_count,
            "identified_items": self.identified_items,
            "identified_percent": self.identified_percent,
            "manifest_items": self.manifest_items,
            "network_calls": 0,
            "new_requests_after_revocation": 0,
            "observations": self.observation_count,
            "physical_deletes": 0,
            "platform_killed": self.platform_killed,
            "platform_requests": 0,
            "private_path_emitted": False,
            "relations": self.relation_count,
            "removed_relations": 0,
            "authorization_cleanup_required": self.authorization_cleanup_required,
            "retention": {
                "deletion_receipt_ready": self.deletion_receipt_ready,
                "delete_required": self.authorization_cleanup_required,
                "policy_ready": self.retention_policy_ready,
                "receipt_sha256": self.retention_receipt_sha256,
            },
            "rate_limit": {
                "automatic_retry": False,
                "proxy_rotations": 0,
                "rate_limited": self.rate_limited,
                "retry_after_seconds": self.retry_after_seconds,
                "retry_not_before": self.retry_not_before,
            },
            "scan_ref_sha256": self.scan_ref_sha256,
            "schema_version": "1.0",
            "selected_manifest_complete": self.checkpoint_state == "complete",
            "silent_losses": 0,
            "source_list_complete": False,
            "task_id": TASK_ID,
        }


def build_taobao_canary_plan(max_items: int = CANARY_ITEM_LIMIT) -> dict[str, Any]:
    if not isinstance(max_items, int) or isinstance(max_items, bool) or max_items != CANARY_ITEM_LIMIT:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "The Taobao Canary is fixed to 20 selected items")
    return {
        "acceptance_ids": ["ACC.x2n.tb.001", "ACC.x2n.tb.002"],
        "adapter": ADAPTER_NAME,
        "approved_budget_units": 0,
        "automatic_pagination": False,
        "automatic_scroll": False,
        "canonical_public_route": "UNVERIFIED_DISABLED",
        "current_capability": "BLOCKED_BUDGET_ZERO_SCOPE_RETENTION_PRICE_QUOTA_UNKNOWN",
        "current_price_state": "UNKNOWN_NOT_APPROVED",
        "current_quota_state": "UNKNOWN_NOT_APPROVED",
        "execution": "NOT_RUN",
        "feature_flag": "taobao_selected_collection",
        "max_items": CANARY_ITEM_LIMIT,
        "official_endpoint": "taobao.item.get",
        "official_scope": "minimum_num_iid_and_title_fields_plus_owner_oauth",
        "owner_oauth_required": True,
        "minimum_necessary_scope_required": True,
        "preconditions": [
            "approved_taobao_application",
            "owner_oauth_active",
            "item_get_scope_confirmed",
            "pricing_snapshot_owner_approved",
            "quota_snapshot_owner_approved",
            "nonzero_owner_budget_approved",
            "sanitized_transport_attested",
            "official_top_transport_attested",
            "local_only_storage_attested",
            "canonical_route_attested",
            "purpose_scope_disclosure_approved",
            "retention_period_approved",
            "delete_revoke_flow_ready",
            "deletion_receipt_ready",
            "private_gold_manifest_ready",
            "policy_recheck_current",
            "stop_control_visible",
        ],
        "proxy_rotation": False,
        "retry_after_required_on_429": True,
        "production_enabled": PRODUCTION_ENABLED,
        "real_account_execution": "NOT_RUN",
        "relation_semantics": "owner_explicit_selection_saved_current_not_taobao_favorite",
        "rollback": "disable_taobao_selected_collection_keep_current_page",
        "source_kind": SOURCE_KIND,
        "task_id": TASK_ID,
        "transport": "NONE_IN_ADAPTERS_009",
    }


class TaobaoSelectedAdapter:
    """Atomic writer for one sanitized, owner-confirmed Taobao selection."""

    def __init__(self, store: CanonicalStore, *, fault_injector: FaultInjector | None = None) -> None:
        self.store = store
        self._fault_injector = fault_injector

    def _fault(self, label: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector(label)

    @staticmethod
    def _initial_cursor(
        owner_selection_id: str,
        selection_manifest_sha256: str,
        capability: TaobaoCapabilityReceipt,
    ) -> dict[str, Any]:
        return {
            "approved_budget_units": capability.approved_budget_units,
            "authorization_cleanup_required": False,
            "capability_receipt_sha256": capability.receipt_hash(),
            "retention_receipt_sha256": capability.retention_ref_sha256,
            "retention_policy_ready": all(
                (
                    capability.purpose_scope_disclosure_approved,
                    capability.retention_period_approved,
                    capability.delete_revoke_flow_ready,
                    capability.deletion_receipt_ready,
                )
            ),
            "deletion_receipt_ready": capability.deletion_receipt_ready,
            "error_evidence_count": 0,
            "identified_items": 0,
            "last_batch_hash": None,
            "last_error_codes": [],
            "last_outcome": "not_started",
            "last_sequence": None,
            "manifest_items": 0,
            "next_sequence": 0,
            "owner_selection_id": owner_selection_id,
            "platform_killed": False,
            "platform_requests": 0,
            "projected_cost_units": capability.projected_cost_units,
            "rate_limited": False,
            "remaining_quota_requests": capability.remaining_quota_requests,
            "retry_after_seconds": None,
            "retry_not_before": None,
            "selection_manifest_sha256": selection_manifest_sha256,
            "source_kind": SOURCE_KIND,
        }

    @staticmethod
    def _cursor(raw: str | None) -> dict[str, Any]:
        try:
            value = json.loads(raw or "")
        except json.JSONDecodeError:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Taobao checkpoint cursor is invalid") from None
        expected = {
            "approved_budget_units",
            "authorization_cleanup_required",
            "capability_receipt_sha256",
            "retention_receipt_sha256",
            "retention_policy_ready",
            "deletion_receipt_ready",
            "error_evidence_count",
            "identified_items",
            "last_batch_hash",
            "last_error_codes",
            "last_outcome",
            "last_sequence",
            "manifest_items",
            "next_sequence",
            "owner_selection_id",
            "platform_killed",
            "platform_requests",
            "projected_cost_units",
            "rate_limited",
            "remaining_quota_requests",
            "retry_after_seconds",
            "retry_not_before",
            "selection_manifest_sha256",
            "source_kind",
        }
        if not isinstance(value, dict) or set(value) != expected:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Taobao checkpoint cursor is invalid")
        required_integers = (
            "approved_budget_units",
            "error_evidence_count",
            "identified_items",
            "manifest_items",
            "next_sequence",
            "platform_requests",
        )
        optional_integers = ("projected_cost_units", "remaining_quota_requests", "retry_after_seconds")
        valid_integers = all(
            isinstance(value.get(field), int) and not isinstance(value.get(field), bool) and value[field] >= 0
            for field in required_integers
        ) and all(
            value.get(field) is None
            or (isinstance(value.get(field), int) and not isinstance(value.get(field), bool) and value[field] >= 0)
            for field in optional_integers
        )
        last_sequence = value.get("last_sequence")
        valid_last_sequence = last_sequence is None or (
            isinstance(last_sequence, int) and not isinstance(last_sequence, bool) and last_sequence == 0
        )
        valid_hashes = all(
            candidate is None or (isinstance(candidate, str) and SHA256.fullmatch(candidate) is not None)
            for candidate in (
                value.get("last_batch_hash"),
                value.get("capability_receipt_sha256"),
                value.get("retention_receipt_sha256"),
            )
        )
        outcomes = {
            "not_started",
            "ready",
            "partial",
            "auth_required",
            "oauth_revoked",
            "budget_blocked",
            "retention_blocked",
            "rate_limited",
            "policy_blocked",
            "empty_unverified",
            "platform_changed",
        }
        killed_outcomes = {
            "auth_required",
            "oauth_revoked",
            "budget_blocked",
            "retention_blocked",
            "policy_blocked",
        }
        is_rate_limited = value.get("last_outcome") == "rate_limited"
        retry_shape = (
            value.get("retry_after_seconds") is not None
            and value.get("retry_after_seconds") <= MAX_RETRY_AFTER_SECONDS
            and _parse_timestamp(value.get("retry_not_before")) is not None
            if is_rate_limited
            else value.get("retry_after_seconds") is None and value.get("retry_not_before") is None
        )
        initial = (
            last_sequence is None
            and value.get("last_batch_hash") is None
            and value.get("last_outcome") == "not_started"
            and value.get("next_sequence") == 0
            and value.get("manifest_items") == 0
            and value.get("identified_items") == 0
            and value.get("error_evidence_count") == 0
            and value.get("last_error_codes") == []
            and value.get("platform_killed") is False
            and value.get("rate_limited") is False
            and value.get("authorization_cleanup_required") is False
            and retry_shape
        )
        progressed = (
            last_sequence == 0
            and value.get("last_batch_hash") is not None
            and value.get("last_outcome") in outcomes - {"not_started"}
            and value.get("next_sequence") in {0, 1}
            and value.get("identified_items") <= value.get("manifest_items") <= CANARY_ITEM_LIMIT
            and value.get("error_evidence_count") >= len(value.get("last_error_codes", []))
            and value.get("next_sequence") == (1 if value.get("last_outcome") == "ready" else 0)
            and value.get("platform_killed") == (value.get("last_outcome") in killed_outcomes)
            and value.get("authorization_cleanup_required") == (value.get("last_outcome") == "oauth_revoked")
            and value.get("rate_limited") is is_rate_limited
            and retry_shape
        )
        if (
            not valid_integers
            or not valid_last_sequence
            or not valid_hashes
            or value.get("platform_requests") != 0
            or not isinstance(value.get("last_error_codes"), list)
            or any(code not in {item.value for item in ErrorCode} for code in value.get("last_error_codes", []))
            or value.get("last_outcome") not in outcomes
            or any(
                type(value.get(field)) is not bool
                for field in (
                    "authorization_cleanup_required",
                    "deletion_receipt_ready",
                    "platform_killed",
                    "rate_limited",
                    "retention_policy_ready",
                )
            )
            or not isinstance(value.get("owner_selection_id"), str)
            or SELECTION_ID.fullmatch(value["owner_selection_id"]) is None
            or not isinstance(value.get("selection_manifest_sha256"), str)
            or SHA256.fullmatch(value["selection_manifest_sha256"]) is None
            or value.get("source_kind") != SOURCE_KIND
            or not (initial or progressed)
        ):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Taobao checkpoint cursor is invalid")
        return value

    def begin_scan(
        self,
        scan_id: str,
        *,
        account_ref_hash: str,
        owner_selection_id: str,
        selection_manifest_sha256: str,
        capability: TaobaoCapabilityReceipt,
        started_at: datetime,
    ) -> TaobaoSelectedReceipt:
        identity = _identity(scan_id)
        decision = evaluate_taobao_capability(capability)
        if not decision.offline_mapping_permitted:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Taobao selected collection remains disabled")
        if not isinstance(account_ref_hash, str) or SHA256.fullmatch(account_ref_hash) is None:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Taobao account reference is invalid")
        if not isinstance(owner_selection_id, str) or SELECTION_ID.fullmatch(owner_selection_id) is None:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Taobao owner selection identity is invalid")
        if not isinstance(selection_manifest_sha256, str) or SHA256.fullmatch(selection_manifest_sha256) is None:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Taobao selection manifest reference is invalid")
        timestamp = _timestamp(started_at)
        input_hash = _sha256(
            {
                "account_ref_hash": account_ref_hash,
                "capability_receipt_hash": capability.receipt_hash(),
                "owner_selection_id": owner_selection_id,
                "selection_manifest_sha256": selection_manifest_sha256,
                "source_kind": SOURCE_KIND,
            }
        )
        with self.store._transaction() as connection:
            run = connection.execute(
                "SELECT run_kind, state, input_manifest_hash FROM run_record WHERE run_id = ?",
                (identity["run_id"],),
            ).fetchone()
            checkpoint = connection.execute(
                "SELECT * FROM checkpoint WHERE checkpoint_id = ?",
                (identity["checkpoint_id"],),
            ).fetchone()
            if (run is None) != (checkpoint is None):
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Taobao scan graph is incomplete")
            created = run is None
            if created:
                connection.execute(
                    "INSERT OR IGNORE INTO account_ref(account_ref_hash, platform, created_at) VALUES (?, ?, ?)",
                    (account_ref_hash, Platform.TAOBAO.value, timestamp),
                )
                connection.execute(
                    """
                    INSERT INTO run_record(
                        run_id, run_kind, state, input_manifest_hash, started_at, finished_at, created_at
                    ) VALUES (?, ?, 'running', ?, ?, NULL, ?)
                    """,
                    (identity["run_id"], RUN_KIND, input_hash, timestamp, timestamp),
                )
                connection.execute(
                    """
                    INSERT INTO checkpoint(
                        checkpoint_id, adapter_name, adapter_version, account_ref_hash, relation_type,
                        cursor_kind, cursor_value_private, last_stable_content_id, full_scan_id,
                        observed_count, completion_confidence, resume_compatibility_version, state,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'saved_current', 'owner_explicit_selection', ?, NULL, NULL,
                              0, 0.0, ?, 'active', ?, ?)
                    """,
                    (
                        identity["checkpoint_id"],
                        ADAPTER_NAME,
                        ADAPTER_VERSION,
                        account_ref_hash,
                        _canonical_json(
                            self._initial_cursor(owner_selection_id, selection_manifest_sha256, capability)
                        ),
                        RESUME_COMPATIBILITY_VERSION,
                        timestamp,
                        timestamp,
                    ),
                )
                run = connection.execute(
                    "SELECT run_kind, state, input_manifest_hash FROM run_record WHERE run_id = ?",
                    (identity["run_id"],),
                ).fetchone()
                checkpoint = connection.execute(
                    "SELECT * FROM checkpoint WHERE checkpoint_id = ?",
                    (identity["checkpoint_id"],),
                ).fetchone()
            if run is None or checkpoint is None:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Taobao scan graph is unavailable")
            if (
                run["run_kind"] != RUN_KIND
                or run["input_manifest_hash"] != input_hash
                or checkpoint["adapter_name"] != ADAPTER_NAME
                or checkpoint["adapter_version"] != ADAPTER_VERSION
                or checkpoint["account_ref_hash"] != account_ref_hash
                or checkpoint["relation_type"] != RelationType.SAVED_CURRENT.value
                or checkpoint["resume_compatibility_version"] != RESUME_COMPATIBILITY_VERSION
                or checkpoint["full_scan_id"] is not None
            ):
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Taobao scan identity conflicts")
            cursor = self._cursor(checkpoint["cursor_value_private"])
            if (
                cursor["owner_selection_id"] != owner_selection_id
                or cursor["selection_manifest_sha256"] != selection_manifest_sha256
            ):
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Taobao selection identity conflicts")
            self._validate_graph_state(str(run["state"]), str(checkpoint["state"]), cursor)
            return self._receipt(connection, scan_id, checkpoint, disposition="applied" if created else "replayed")

    @staticmethod
    def _validate_graph_state(run_state: str, checkpoint_state: str, cursor: Mapping[str, Any]) -> None:
        valid = {
            ("running", "active", False),
            ("succeeded", "complete", False),
            ("cancelled", "invalidated", True),
        }
        if (run_state, checkpoint_state, cursor.get("platform_killed")) not in valid:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Taobao scan graph state is inconsistent")

    @staticmethod
    def _content(connection: Any, item: TaobaoSelectedItem, observed_at: datetime) -> CanonicalContent:
        content_key = build_content_key(Platform.TAOBAO, item.num_iid)
        row = connection.execute("SELECT payload_json FROM content WHERE content_key = ?", (content_key,)).fetchone()
        first = observed_at
        version = 1
        if row is not None:
            stored = CanonicalContent.model_validate_json(row["payload_json"])
            if observed_at < stored.last_observed_at:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Taobao content time moved backwards")
            first = stored.first_observed_at
            version = stored.record_version if observed_at == stored.last_observed_at else stored.record_version + 1
        return CanonicalContent(
            schema_version="1.0",
            content_key=content_key,
            platform=Platform.TAOBAO,
            platform_content_id=item.num_iid,
            canonical_source_url=_canonical_page_url(),
            content_type=ContentType.UNKNOWN,
            title=item.title,
            description=None,
            author_name=None,
            author_platform_id=None,
            published_at=None,
            content_hash=_sha256(item.facts()),
            first_observed_at=first,
            last_observed_at=observed_at,
            record_version=version,
            status=ContentStatus.ACTIVE,
        )

    @staticmethod
    def _relation(
        connection: Any,
        item: TaobaoSelectedItem,
        *,
        account_ref_hash: str,
        scan_receipt_id: str,
        observed_at: datetime,
    ) -> UserRelation:
        content_key = build_content_key(Platform.TAOBAO, item.num_iid)
        relation_key = build_relation_key(
            account_ref_hash,
            content_key,
            RelationType.SAVED_CURRENT,
        )
        row = connection.execute(
            "SELECT payload_json FROM user_relation WHERE relation_key = ?",
            (relation_key,),
        ).fetchone()
        first = observed_at
        if row is not None:
            stored = UserRelation.model_validate_json(row["payload_json"])
            if observed_at < stored.last_seen_at:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Taobao relation time moved backwards")
            first = stored.first_seen_at
        return UserRelation(
            schema_version="1.0",
            relation_key=relation_key,
            account_ref_hash=account_ref_hash,
            content_key=content_key,
            relation_type=RelationType.SAVED_CURRENT,
            source_collection_id=None,
            source_collection_name_private=None,
            first_seen_at=first,
            last_seen_at=observed_at,
            status=RelationStatus.ACTIVE,
            confirmed_by=ConfirmationSource.OWNER,
            scan_receipt_id=scan_receipt_id,
        )

    @staticmethod
    def _observation(
        item: TaobaoSelectedItem,
        *,
        scan_id: str,
        run_id: str,
        observed_at: datetime,
    ) -> SourceObservation:
        facts_hash = _sha256(item.facts())
        observation_id = f"obs_{uuid.uuid5(_scan_uuid(scan_id), f'taobao-owner-selected:{facts_hash}').hex}"
        fields = (
            CanonicalField.PLATFORM_CONTENT_ID,
            CanonicalField.CANONICAL_SOURCE_URL,
            CanonicalField.CONTENT_TYPE,
            CanonicalField.TITLE,
            CanonicalField.PUBLISHED_AT,
        )
        return SourceObservation(
            schema_version="1.0",
            observation_id=observation_id,
            content_key=build_content_key(Platform.TAOBAO, item.num_iid),
            adapter_name=ADAPTER_NAME,
            adapter_version=ADAPTER_VERSION,
            source_method=SourceMethod.SELECTED_COLLECTION,
            observed_at=observed_at,
            raw_text_hash=facts_hash,
            normalized_fields=fields,
            field_provenance=(
                FieldProvenance(
                    field=CanonicalField.PLATFORM_CONTENT_ID,
                    source=FieldSource.ADAPTER,
                    status=FieldStatus.PRESENT,
                    confidence=1.0,
                ),
                FieldProvenance(
                    field=CanonicalField.CANONICAL_SOURCE_URL,
                    source=FieldSource.DERIVED,
                    status=FieldStatus.PRESENT,
                    confidence=1.0,
                ),
                FieldProvenance(
                    field=CanonicalField.CONTENT_TYPE,
                    source=FieldSource.DERIVED,
                    status=FieldStatus.UNKNOWN,
                    confidence=0.0,
                ),
                FieldProvenance(
                    field=CanonicalField.TITLE,
                    source=FieldSource.ADAPTER,
                    status=FieldStatus.PRESENT,
                    confidence=1.0,
                ),
                FieldProvenance(
                    field=CanonicalField.PUBLISHED_AT,
                    source=FieldSource.ADAPTER,
                    status=FieldStatus.UNKNOWN,
                    confidence=0.0,
                ),
            ),
            completeness=0.6,
            warning_codes=(),
            ephemeral_media_ref_ids=(),
            run_id=run_id,
        )

    def commit_batch(self, scan_id: str, batch: TaobaoSelectedBatch) -> TaobaoSelectedReceipt:
        identity = _identity(scan_id)
        batch_hash = batch.batch_hash()
        observed_at = _utc(batch.observed_at)
        timestamp = _timestamp(observed_at)
        with self.store._transaction() as connection:
            checkpoint = connection.execute(
                "SELECT * FROM checkpoint WHERE checkpoint_id = ?",
                (identity["checkpoint_id"],),
            ).fetchone()
            run = connection.execute(
                "SELECT state FROM run_record WHERE run_id = ?",
                (identity["run_id"],),
            ).fetchone()
            if checkpoint is None or run is None:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Taobao scan is not initialized")
            cursor = self._cursor(checkpoint["cursor_value_private"])
            self._validate_graph_state(str(run["state"]), str(checkpoint["state"]), cursor)
            if (
                batch.owner_selection_id != cursor["owner_selection_id"]
                or batch.selection_manifest_sha256 != cursor["selection_manifest_sha256"]
            ):
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Taobao batch selection conflicts")
            if cursor["last_sequence"] == batch.sequence and cursor["last_batch_hash"] == batch_hash:
                return self._receipt(connection, scan_id, checkpoint, disposition="replayed")
            if checkpoint["state"] != "active" or run["state"] != "running":
                raise X2NRuntimeError(
                    ErrorCode.DATA_INTEGRITY_FAILED, "Taobao completed scan cannot accept another batch"
                )
            if batch.sequence != cursor["next_sequence"]:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Taobao batch is not the checkpoint successor")
            if timestamp < str(checkpoint["updated_at"]):
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Taobao checkpoint time moved backwards")
            if cursor["rate_limited"]:
                retry_not_before = _parse_timestamp(cursor["retry_not_before"])
                if retry_not_before is None or observed_at < retry_not_before:
                    raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Taobao Retry-After hold is still active")

            account_ref_hash = str(checkpoint["account_ref_hash"])
            content_writes = relation_writes = observation_writes = 0
            if batch.status == "ready":
                for index, item in enumerate(batch.items):
                    content = self._content(connection, item, observed_at)
                    if self.store._upsert_content(connection, content, timestamp) is not WriteDisposition.UNCHANGED:
                        content_writes += 1
                    relation = self._relation(
                        connection,
                        item,
                        account_ref_hash=account_ref_hash,
                        scan_receipt_id=identity["scan_receipt_id"],
                        observed_at=observed_at,
                    )
                    if (
                        self.store._upsert_relation(connection, relation, Platform.TAOBAO.value, timestamp)
                        is not WriteDisposition.UNCHANGED
                    ):
                        relation_writes += 1
                    observation = self._observation(
                        item,
                        scan_id=scan_id,
                        run_id=identity["run_id"],
                        observed_at=observed_at,
                    )
                    if (
                        self.store._append_observation(connection, observation, timestamp)
                        is not WriteDisposition.UNCHANGED
                    ):
                        observation_writes += 1
                    self._fault(f"after_item_{index}")

            killed = batch.status in {
                "auth_required",
                "oauth_revoked",
                "budget_blocked",
                "retention_blocked",
                "policy_blocked",
            }
            state = "complete" if batch.status == "ready" else "invalidated" if killed else "active"
            cursor_kind = (
                "bounded_selection_complete"
                if batch.status == "ready"
                else "oauth_revoked_cleanup_required"
                if batch.status == "oauth_revoked"
                else "budget_gate_killed"
                if batch.status == "budget_blocked"
                else "retention_gate_killed"
                if batch.status == "retention_blocked"
                else "rate_limited_retry_after"
                if batch.status == "rate_limited"
                else "platform_policy_killed"
                if killed
                else "owner_selection_blocked"
            )
            retry_after_seconds: int | None = None
            retry_not_before_value: str | None = None
            if batch.status == "rate_limited":
                assert batch.retry_after is not None
                retry_after_seconds, retry_not_before = _retry_not_before(batch.retry_after, observed_at)
                retry_not_before_value = _timestamp(retry_not_before)
            identified_items = len(batch.items)
            observed_count = int(
                connection.execute(
                    "SELECT COUNT(DISTINCT content_key) FROM source_observation WHERE run_id = ?",
                    (identity["run_id"],),
                ).fetchone()[0]
            )
            cursor.update(
                {
                    "error_evidence_count": cursor["error_evidence_count"] + len(batch.error_codes),
                    "identified_items": identified_items,
                    "last_batch_hash": batch_hash,
                    "last_error_codes": list(batch.error_codes),
                    "last_outcome": batch.status,
                    "last_sequence": batch.sequence,
                    "manifest_items": batch.selected_manifest_count,
                    "next_sequence": 1 if batch.status == "ready" else 0,
                    "platform_killed": killed,
                    "authorization_cleanup_required": batch.status == "oauth_revoked",
                    "rate_limited": batch.status == "rate_limited",
                    "retry_after_seconds": retry_after_seconds,
                    "retry_not_before": retry_not_before_value,
                }
            )
            last_stable = batch.items[-1].num_iid if batch.status == "ready" else checkpoint["last_stable_content_id"]
            self._fault("before_checkpoint")
            updated = connection.execute(
                """
                UPDATE checkpoint SET
                    cursor_kind = ?, cursor_value_private = ?, last_stable_content_id = ?, full_scan_id = NULL,
                    observed_count = ?, completion_confidence = ?, state = ?, updated_at = ?
                WHERE checkpoint_id = ? AND state = 'active'
                """,
                (
                    cursor_kind,
                    _canonical_json(cursor),
                    last_stable,
                    observed_count,
                    1.0 if batch.status == "ready" else 0.0,
                    state,
                    timestamp,
                    identity["checkpoint_id"],
                ),
            )
            if updated.rowcount != 1:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Taobao checkpoint transition conflicted")
            if state == "complete":
                run_update = connection.execute(
                    "UPDATE run_record SET state = 'succeeded', finished_at = ? WHERE run_id = ? AND state = 'running'",
                    (timestamp, identity["run_id"]),
                )
                if run_update.rowcount != 1:
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Taobao Run completion conflicted")
            elif state == "invalidated":
                run_update = connection.execute(
                    "UPDATE run_record SET state = 'cancelled', finished_at = ? WHERE run_id = ? AND state = 'running'",
                    (timestamp, identity["run_id"]),
                )
                if run_update.rowcount != 1:
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Taobao platform Kill conflicted")
            self._fault("after_checkpoint")
            refreshed = connection.execute(
                "SELECT * FROM checkpoint WHERE checkpoint_id = ?",
                (identity["checkpoint_id"],),
            ).fetchone()
            if refreshed is None:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Taobao checkpoint disappeared")
            expected_writes = len(batch.items) if batch.status == "ready" else 0
            if any(value > expected_writes for value in (content_writes, relation_writes, observation_writes)):
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Taobao write cardinality is invalid")
            return self._receipt(connection, scan_id, refreshed, disposition="applied")

    def checkpoint(self, scan_id: str) -> TaobaoSelectedReceipt:
        identity = _identity(scan_id)
        with self.store._file_lock(exclusive=False):
            connection = self.store._open(writable=False)
            try:
                checkpoint = connection.execute(
                    "SELECT * FROM checkpoint WHERE checkpoint_id = ?",
                    (identity["checkpoint_id"],),
                ).fetchone()
                if checkpoint is None:
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Taobao checkpoint is unavailable")
                return self._receipt(connection, scan_id, checkpoint, disposition="replayed")
            finally:
                connection.close()

    def _receipt(
        self,
        connection: Any,
        scan_id: str,
        checkpoint: Any,
        *,
        disposition: Literal["applied", "replayed"],
    ) -> TaobaoSelectedReceipt:
        identity = _identity(scan_id)
        cursor = self._cursor(checkpoint["cursor_value_private"])
        run = connection.execute("SELECT state FROM run_record WHERE run_id = ?", (identity["run_id"],)).fetchone()
        if run is None:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Taobao Run is unavailable")
        self._validate_graph_state(str(run["state"]), str(checkpoint["state"]), cursor)
        relation_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM user_relation WHERE scan_receipt_id = ?",
                (identity["scan_receipt_id"],),
            ).fetchone()[0]
        )
        observation_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM source_observation WHERE run_id = ?",
                (identity["run_id"],),
            ).fetchone()[0]
        )
        manifest_items = int(cursor["manifest_items"])
        identified_items = int(cursor["identified_items"])
        percent = round(identified_items * 100 / manifest_items, 2) if manifest_items else 0.0
        return TaobaoSelectedReceipt(
            scan_ref_sha256=hashlib.sha256(scan_id.encode("ascii")).hexdigest(),
            disposition=disposition,
            checkpoint_state=checkpoint["state"],
            cursor_kind=checkpoint["cursor_kind"],
            next_sequence=int(cursor["next_sequence"]),
            manifest_items=manifest_items,
            identified_items=identified_items,
            identified_percent=percent,
            relation_count=relation_count,
            observation_count=observation_count,
            error_evidence_count=int(cursor["error_evidence_count"]),
            platform_killed=bool(cursor["platform_killed"]),
            authorization_cleanup_required=bool(cursor["authorization_cleanup_required"]),
            rate_limited=bool(cursor["rate_limited"]),
            retry_not_before=cursor["retry_not_before"],
            retry_after_seconds=cursor["retry_after_seconds"],
            approved_budget_units=int(cursor["approved_budget_units"]),
            projected_cost_units=cursor["projected_cost_units"],
            remaining_quota_requests=cursor["remaining_quota_requests"],
            capability_receipt_sha256=cursor["capability_receipt_sha256"],
            retention_receipt_sha256=cursor["retention_receipt_sha256"],
            retention_policy_ready=bool(cursor["retention_policy_ready"]),
            deletion_receipt_ready=bool(cursor["deletion_receipt_ready"]),
        )


class TaobaoSelectedBatchCoordinator:
    """Apply the single owner action under the global non-waiting Adapter guard."""

    def __init__(self, adapter: TaobaoSelectedAdapter, guard: AdapterExecutionGate) -> None:
        self.adapter = adapter
        self.guard = guard

    def apply_owner_action(
        self,
        scan_id: str,
        batch: TaobaoSelectedBatch,
        *,
        monotonic_batch_time: float,
        monotonic_observation_time: float,
    ) -> TaobaoSelectedReceipt:
        with self.guard.acquire(Platform.TAOBAO.value, now=monotonic_batch_time) as lease:
            lease.permit_item_observation(now=monotonic_observation_time)
            return self.adapter.commit_batch(scan_id, batch)
