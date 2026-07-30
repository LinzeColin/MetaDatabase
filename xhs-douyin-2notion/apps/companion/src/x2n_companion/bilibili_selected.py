"""Fail-closed Bilibili owner-selection mapping for one bounded manifest.

The module has no network transport and no browser automation.  It consumes one
strictly sanitized, explicitly selected manifest and maps it atomically into the
Canonical Store.  The only currently documented source shape is an authorized
uploader's own video-manuscript list; it is never represented as a Bilibili like
or favorite relation.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
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


TASK_ID = "TSK.x2n.adapters.006"
ADAPTER_NAME = "bilibili_selected_collection"
ADAPTER_VERSION = "1.0.0"
RESUME_COMPATIBILITY_VERSION = "bilibili-selected-1.0.0"
RUN_KIND = "bilibili_owner_selection_v1"
POLICY_REVISION = "2026-07-23"
SOURCE_KIND = "authorized_uploader_video_manuscripts"
CANARY_ITEM_LIMIT = 20
PRODUCTION_ENABLED = False

SHA256 = re.compile(r"^[0-9a-f]{64}$")
BVID = re.compile(r"^BV[A-Za-z0-9]{10}$")
SELECTION_ID = re.compile(r"^x2nsel_[0-9a-f]{32}$")
BatchStatus = Literal[
    "ready",
    "partial",
    "auth_required",
    "policy_blocked",
    "captcha_required",
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
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Bilibili time requires an explicit timezone")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _timestamp(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.endswith("Z"):
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Bilibili published time is invalid")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Bilibili published time is invalid") from None
    if _timestamp(parsed) != value:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Bilibili published time is not canonical")
    return parsed


def _safe_title(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 500
        or value != " ".join(value.split())
        or re.search(r"[\x00-\x1f\x7f]", value)
        or re.search(r"https?://", value, flags=re.IGNORECASE)
    ):
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Bilibili title is unsafe")
    return value


def _scan_uuid(value: str) -> uuid.UUID:
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, TypeError, ValueError):
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Bilibili scan identity is invalid") from None
    if str(parsed) != value:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Bilibili scan identity is not canonical")
    return parsed


def _identity(scan_id: str) -> dict[str, str]:
    suffix = _scan_uuid(scan_id).hex
    return {
        "checkpoint_id": f"checkpoint_bilisel_{suffix}",
        "run_id": f"run_bilisel_{suffix}",
        "scan_receipt_id": f"receipt_bilisel_{suffix}",
    }


def _canonical_page_url(bvid: str) -> str:
    return f"https://www.bilibili.com/video/{bvid}"


@dataclass(frozen=True)
class BilibiliCapabilityReceipt:
    """Credential-free capability attestation; it never carries OAuth material."""

    environment: Literal["ci_synthetic", "owner_runtime"]
    source_kind: Literal["authorized_uploader_video_manuscripts"]
    policy_revision: Literal["2026-07-23"]
    authorization_ref_sha256: str
    application_approved: bool
    owner_authorized: bool
    arc_base_granted: bool
    written_automation_permission: bool
    transport_available: bool
    credential_material_present: Literal[False] = False

    def __post_init__(self) -> None:
        if self.environment not in {"ci_synthetic", "owner_runtime"}:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Bilibili capability environment is invalid")
        if self.source_kind != SOURCE_KIND or self.policy_revision != POLICY_REVISION:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Bilibili capability policy is stale")
        if (
            not isinstance(self.authorization_ref_sha256, str)
            or SHA256.fullmatch(self.authorization_ref_sha256) is None
        ):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Bilibili authorization reference is invalid")
        flags = (
            self.application_approved,
            self.owner_authorized,
            self.arc_base_granted,
            self.written_automation_permission,
            self.transport_available,
            self.credential_material_present,
        )
        if any(type(flag) is not bool for flag in flags) or self.credential_material_present is not False:
            raise X2NRuntimeError(ErrorCode.SECURITY_INJECTION_BLOCKED, "Bilibili capability flags are invalid")
        if self.environment == "ci_synthetic" and any(flags[:-1]):
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Synthetic capability cannot claim real authorization")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "BilibiliCapabilityReceipt":
        expected = {
            "application_approved",
            "arc_base_granted",
            "authorization_ref_sha256",
            "credential_material_present",
            "environment",
            "owner_authorized",
            "policy_revision",
            "source_kind",
            "transport_available",
            "written_automation_permission",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise X2NRuntimeError(ErrorCode.UNKNOWN_FIELD, "Bilibili capability shape is invalid")
        return cls(**dict(value))  # type: ignore[arg-type]

    def receipt_hash(self) -> str:
        return _sha256(
            {
                "application_approved": self.application_approved,
                "arc_base_granted": self.arc_base_granted,
                "authorization_ref_sha256": self.authorization_ref_sha256,
                "credential_material_present": self.credential_material_present,
                "environment": self.environment,
                "owner_authorized": self.owner_authorized,
                "policy_revision": self.policy_revision,
                "source_kind": self.source_kind,
                "transport_available": self.transport_available,
                "written_automation_permission": self.written_automation_permission,
            }
        )


@dataclass(frozen=True)
class BilibiliCapabilityDecision:
    status: str
    offline_mapping_permitted: bool
    platform_requests_permitted: bool
    missing_requirements: tuple[str, ...]

    def safe_dict(self) -> dict[str, Any]:
        return {
            "missing_requirements": list(self.missing_requirements),
            "offline_mapping_permitted": self.offline_mapping_permitted,
            "platform_requests_permitted": self.platform_requests_permitted,
            "production_enabled": PRODUCTION_ENABLED,
            "status": self.status,
        }


def evaluate_bilibili_capability(receipt: BilibiliCapabilityReceipt) -> BilibiliCapabilityDecision:
    if receipt.environment == "ci_synthetic":
        return BilibiliCapabilityDecision("PASS_CI_SYNTHETIC", True, False, ())
    requirements = {
        "application_approval": receipt.application_approved,
        "arc_base_grant": receipt.arc_base_granted,
        "owner_authorization": receipt.owner_authorized,
        "sanitized_transport": receipt.transport_available,
        "written_automation_permission": receipt.written_automation_permission,
    }
    missing = tuple(sorted(name for name, present in requirements.items() if not present))
    if missing:
        return BilibiliCapabilityDecision("BLOCKED_MISSING_AUTHORIZATION", False, False, missing)
    return BilibiliCapabilityDecision("BLOCKED_FEATURE_DISABLED", False, False, ("production_feature_flag",))


@dataclass(frozen=True)
class BilibiliSelectedItem:
    bvid: str
    title: str
    published_at: datetime | None
    content_type: Literal["video"] = "video"

    def __post_init__(self) -> None:
        if not isinstance(self.bvid, str) or BVID.fullmatch(self.bvid) is None:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Bilibili bvid is invalid")
        _safe_title(self.title)
        if self.published_at is not None:
            _utc(self.published_at)
        if self.content_type != "video":
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Only documented video manuscripts are supported")

    def facts(self) -> dict[str, Any]:
        return {
            "bvid": self.bvid,
            "canonical_page_url": _canonical_page_url(self.bvid),
            "content_type": self.content_type,
            "published_at": _timestamp(self.published_at) if self.published_at else None,
            "title": self.title,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "BilibiliSelectedItem":
        expected = {"bvid", "canonical_page_url", "content_type", "published_at", "title"}
        if not isinstance(value, Mapping) or set(value) != expected:
            raise X2NRuntimeError(ErrorCode.UNKNOWN_FIELD, "Bilibili item shape is invalid")
        item = cls(
            bvid=value["bvid"],
            title=value["title"],
            published_at=_parse_timestamp(value["published_at"]),
            content_type=value["content_type"],
        )
        if value["canonical_page_url"] != _canonical_page_url(item.bvid):
            raise X2NRuntimeError(ErrorCode.URL_REJECTED, "Bilibili canonical page address is invalid")
        return item


@dataclass(frozen=True)
class BilibiliSelectedBatch:
    sequence: int
    status: BatchStatus
    selected_manifest_count: int
    items: tuple[BilibiliSelectedItem, ...]
    error_codes: tuple[str, ...]
    observed_at: datetime
    owner_selection_id: str
    selection_manifest_sha256: str
    source_kind: Literal["authorized_uploader_video_manuscripts"] = SOURCE_KIND
    explicit_owner_action: Literal[True] = True
    automatic_pagination: Literal[False] = False
    automatic_scroll: Literal[False] = False

    def __post_init__(self) -> None:
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence != 0:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Bilibili selection permits exactly one bounded batch")
        if self.status not in {
            "ready",
            "partial",
            "auth_required",
            "policy_blocked",
            "captcha_required",
            "empty_unverified",
            "platform_changed",
        }:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Bilibili batch status is invalid")
        if self.source_kind != SOURCE_KIND:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Bilibili source kind is unsupported")
        if (
            self.explicit_owner_action is not True
            or self.automatic_pagination is not False
            or self.automatic_scroll is not False
        ):
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Bilibili batch requires one explicit no-pagination action")
        if not isinstance(self.owner_selection_id, str) or SELECTION_ID.fullmatch(self.owner_selection_id) is None:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Bilibili owner selection identity is invalid")
        if (
            not isinstance(self.selection_manifest_sha256, str)
            or SHA256.fullmatch(self.selection_manifest_sha256) is None
        ):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Bilibili selection manifest reference is invalid")
        if (
            not isinstance(self.selected_manifest_count, int)
            or isinstance(self.selected_manifest_count, bool)
            or not 0 <= self.selected_manifest_count <= CANARY_ITEM_LIMIT
            or len(self.items) > CANARY_ITEM_LIMIT
        ):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Bilibili selection boundary is invalid")
        if len({item.bvid for item in self.items}) != len(self.items):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Bilibili selection contains duplicate items")
        allowed_errors = {item.value for item in ErrorCode}
        if any(code not in allowed_errors for code in self.error_codes):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Bilibili error evidence is invalid")
        if self.status == "ready":
            if not self.items or self.error_codes or len(self.items) != self.selected_manifest_count:
                raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Bilibili ready manifest is incomplete")
        elif self.status == "partial":
            if (
                not self.items
                or not self.error_codes
                or len(self.items) >= self.selected_manifest_count
                or len(self.items) + len(self.error_codes) != self.selected_manifest_count
            ):
                raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Bilibili partial manifest lacks evidence")
        elif self.items or not self.error_codes or self.selected_manifest_count != 0:
            raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Bilibili blocked manifest is inconsistent")
        _utc(self.observed_at)

    def batch_hash(self) -> str:
        return _sha256(
            {
                "automatic_pagination": self.automatic_pagination,
                "automatic_scroll": self.automatic_scroll,
                "error_codes": self.error_codes,
                "explicit_owner_action": self.explicit_owner_action,
                "items": [item.facts() for item in self.items],
                "observed_at": _timestamp(self.observed_at),
                "owner_selection_id": self.owner_selection_id,
                "selected_manifest_count": self.selected_manifest_count,
                "selection_manifest_sha256": self.selection_manifest_sha256,
                "sequence": self.sequence,
                "source_kind": self.source_kind,
                "status": self.status,
            }
        )


class BilibiliSelectedIterator:
    """Converts one sanitized owner action; it cannot fetch or request another page."""

    def __init__(self, capability: BilibiliCapabilityReceipt) -> None:
        self.capability = capability

    def one_explicit_batch(self, value: Mapping[str, Any], *, observed_at: datetime) -> BilibiliSelectedBatch:
        decision = evaluate_bilibili_capability(self.capability)
        if not decision.offline_mapping_permitted:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Bilibili selected collection is not authorized")
        expected = {
            "automatic_pagination",
            "automatic_scroll",
            "error_codes",
            "explicit_owner_action",
            "has_more",
            "items",
            "owner_selection_id",
            "page_number",
            "page_size",
            "platform",
            "policy_revision",
            "schema_version",
            "selected_manifest_count",
            "selection_manifest_sha256",
            "source_kind",
            "status",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise X2NRuntimeError(ErrorCode.UNKNOWN_FIELD, "Bilibili sanitized manifest shape is invalid")
        if (
            value.get("schema_version") != "1.0"
            or value.get("platform") != Platform.BILIBILI.value
            or value.get("policy_revision") != POLICY_REVISION
            or value.get("source_kind") != SOURCE_KIND
        ):
            raise X2NRuntimeError(ErrorCode.INVALID_SCHEMA_VERSION, "Bilibili sanitized manifest identity is invalid")
        if (
            type(value.get("page_number")) is not int
            or value.get("page_number") != 1
            or type(value.get("page_size")) is not int
            or value.get("page_size") != CANARY_ITEM_LIMIT
            or type(value.get("has_more")) is not bool
        ):
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Bilibili page contract is not bounded")
        items = value.get("items")
        errors = value.get("error_codes")
        if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Bilibili item list is invalid")
        if not isinstance(errors, Sequence) or isinstance(errors, (str, bytes)):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Bilibili error list is invalid")
        return BilibiliSelectedBatch(
            sequence=0,
            status=value["status"],
            selected_manifest_count=value["selected_manifest_count"],
            items=tuple(BilibiliSelectedItem.from_mapping(item) for item in items),
            error_codes=tuple(errors),
            observed_at=observed_at,
            owner_selection_id=value["owner_selection_id"],
            selection_manifest_sha256=value["selection_manifest_sha256"],
            source_kind=value["source_kind"],
            explicit_owner_action=value["explicit_owner_action"],
            automatic_pagination=value["automatic_pagination"],
            automatic_scroll=value["automatic_scroll"],
        )


@dataclass(frozen=True)
class BilibiliSelectedReceipt:
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
            "disposition": self.disposition,
            "error_evidence_count": self.error_evidence_count,
            "identified_items": self.identified_items,
            "identified_percent": self.identified_percent,
            "manifest_items": self.manifest_items,
            "network_calls": 0,
            "observations": self.observation_count,
            "physical_deletes": 0,
            "platform_killed": self.platform_killed,
            "platform_requests": 0,
            "private_path_emitted": False,
            "relations": self.relation_count,
            "removed_relations": 0,
            "scan_ref_sha256": self.scan_ref_sha256,
            "schema_version": "1.0",
            "selected_manifest_complete": self.checkpoint_state == "complete",
            "silent_losses": 0,
            "source_list_complete": False,
            "task_id": TASK_ID,
        }


def build_bilibili_canary_plan(max_items: int = CANARY_ITEM_LIMIT) -> dict[str, Any]:
    if not isinstance(max_items, int) or isinstance(max_items, bool) or max_items != CANARY_ITEM_LIMIT:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "The Bilibili Canary is fixed to 20 selected items")
    return {
        "acceptance_ids": ["ACC.x2n.bili.001", "ACC.x2n.bili.002"],
        "adapter": ADAPTER_NAME,
        "automatic_pagination": False,
        "automatic_scroll": False,
        "current_capability": "BLOCKED_AUTH_AND_WRITTEN_PERMISSION",
        "execution": "NOT_RUN",
        "feature_flag": "bilibili_selected_collection",
        "max_items": CANARY_ITEM_LIMIT,
        "official_scope": "ARC_BASE",
        "owner_authorization_required": True,
        "preconditions": [
            "approved_bilibili_application",
            "associated_uploader_owner_authorization",
            "arc_base_scope_granted",
            "written_automation_permission",
            "sanitized_transport_attested",
            "private_gold_manifest_ready",
            "policy_recheck_current",
            "revocation_and_delete_route_ready",
            "stop_control_visible",
        ],
        "production_enabled": PRODUCTION_ENABLED,
        "real_account_execution": "NOT_RUN",
        "relation_semantics": "owner_saved_current_not_bilibili_like_or_favorite",
        "rollback": "disable_bilibili_selected_collection_keep_current_page",
        "source_kind": SOURCE_KIND,
        "task_id": TASK_ID,
        "transport": "NONE_IN_ADAPTERS_006",
    }


class BilibiliSelectedAdapter:
    """Atomic writer for one sanitized, owner-confirmed Bilibili selection."""

    def __init__(self, store: CanonicalStore, *, fault_injector: FaultInjector | None = None) -> None:
        self.store = store
        self._fault_injector = fault_injector

    def _fault(self, label: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector(label)

    @staticmethod
    def _initial_cursor(owner_selection_id: str, selection_manifest_sha256: str) -> dict[str, Any]:
        return {
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
            "selection_manifest_sha256": selection_manifest_sha256,
            "source_kind": SOURCE_KIND,
        }

    @staticmethod
    def _cursor(raw: str | None) -> dict[str, Any]:
        try:
            value = json.loads(raw or "")
        except json.JSONDecodeError:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Bilibili checkpoint cursor is invalid") from None
        expected = {
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
            "selection_manifest_sha256",
            "source_kind",
        }
        if not isinstance(value, dict) or set(value) != expected:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Bilibili checkpoint cursor is invalid")
        integer_fields = ("error_evidence_count", "identified_items", "manifest_items", "next_sequence")
        valid_integers = all(
            isinstance(value.get(field), int) and not isinstance(value.get(field), bool) and value[field] >= 0
            for field in integer_fields
        )
        last_sequence = value.get("last_sequence")
        valid_last_sequence = last_sequence is None or (
            isinstance(last_sequence, int) and not isinstance(last_sequence, bool) and last_sequence == 0
        )
        valid_hash = value.get("last_batch_hash") is None or (
            isinstance(value.get("last_batch_hash"), str) and SHA256.fullmatch(value["last_batch_hash"]) is not None
        )
        outcomes = {
            "not_started",
            "ready",
            "partial",
            "auth_required",
            "policy_blocked",
            "captcha_required",
            "empty_unverified",
            "platform_changed",
        }
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
        )
        progressed = (
            last_sequence == 0
            and value.get("last_batch_hash") is not None
            and value.get("last_outcome") in outcomes - {"not_started"}
            and value.get("next_sequence") in {0, 1}
            and value.get("identified_items") <= value.get("manifest_items") <= CANARY_ITEM_LIMIT
            and value.get("error_evidence_count") >= len(value.get("last_error_codes", []))
            and value.get("next_sequence") == (1 if value.get("last_outcome") == "ready" else 0)
            and value.get("platform_killed")
            == (value.get("last_outcome") in {"auth_required", "policy_blocked", "captcha_required"})
        )
        if (
            not valid_integers
            or not valid_last_sequence
            or not valid_hash
            or not isinstance(value.get("last_error_codes"), list)
            or any(code not in {item.value for item in ErrorCode} for code in value.get("last_error_codes", []))
            or value.get("last_outcome") not in outcomes
            or type(value.get("platform_killed")) is not bool
            or not isinstance(value.get("owner_selection_id"), str)
            or SELECTION_ID.fullmatch(value["owner_selection_id"]) is None
            or not isinstance(value.get("selection_manifest_sha256"), str)
            or SHA256.fullmatch(value["selection_manifest_sha256"]) is None
            or value.get("source_kind") != SOURCE_KIND
            or not (initial or progressed)
        ):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Bilibili checkpoint cursor is invalid")
        return value

    def begin_scan(
        self,
        scan_id: str,
        *,
        account_ref_hash: str,
        owner_selection_id: str,
        selection_manifest_sha256: str,
        capability: BilibiliCapabilityReceipt,
        started_at: datetime,
    ) -> BilibiliSelectedReceipt:
        identity = _identity(scan_id)
        decision = evaluate_bilibili_capability(capability)
        if not decision.offline_mapping_permitted:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Bilibili selected collection remains disabled")
        if not isinstance(account_ref_hash, str) or SHA256.fullmatch(account_ref_hash) is None:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Bilibili account reference is invalid")
        if not isinstance(owner_selection_id, str) or SELECTION_ID.fullmatch(owner_selection_id) is None:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Bilibili owner selection identity is invalid")
        if not isinstance(selection_manifest_sha256, str) or SHA256.fullmatch(selection_manifest_sha256) is None:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Bilibili selection manifest reference is invalid")
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
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Bilibili scan graph is incomplete")
            created = run is None
            if created:
                connection.execute(
                    "INSERT OR IGNORE INTO account_ref(account_ref_hash, platform, created_at) VALUES (?, ?, ?)",
                    (account_ref_hash, Platform.BILIBILI.value, timestamp),
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
                        _canonical_json(self._initial_cursor(owner_selection_id, selection_manifest_sha256)),
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
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Bilibili scan graph is unavailable")
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
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Bilibili scan identity conflicts")
            cursor = self._cursor(checkpoint["cursor_value_private"])
            if (
                cursor["owner_selection_id"] != owner_selection_id
                or cursor["selection_manifest_sha256"] != selection_manifest_sha256
            ):
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Bilibili selection identity conflicts")
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
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Bilibili scan graph state is inconsistent")

    @staticmethod
    def _content(connection: Any, item: BilibiliSelectedItem, observed_at: datetime) -> CanonicalContent:
        content_key = build_content_key(Platform.BILIBILI, item.bvid)
        row = connection.execute("SELECT payload_json FROM content WHERE content_key = ?", (content_key,)).fetchone()
        first = observed_at
        version = 1
        if row is not None:
            stored = CanonicalContent.model_validate_json(row["payload_json"])
            if observed_at < stored.last_observed_at:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Bilibili content time moved backwards")
            first = stored.first_observed_at
            version = stored.record_version if observed_at == stored.last_observed_at else stored.record_version + 1
        return CanonicalContent(
            schema_version="1.0",
            content_key=content_key,
            platform=Platform.BILIBILI,
            platform_content_id=item.bvid,
            canonical_source_url=_canonical_page_url(item.bvid),
            content_type=ContentType.VIDEO,
            title=item.title,
            description=None,
            author_name=None,
            author_platform_id=None,
            published_at=item.published_at,
            content_hash=_sha256(item.facts()),
            first_observed_at=first,
            last_observed_at=observed_at,
            record_version=version,
            status=ContentStatus.ACTIVE,
        )

    @staticmethod
    def _relation(
        connection: Any,
        item: BilibiliSelectedItem,
        *,
        account_ref_hash: str,
        owner_selection_id: str,
        scan_receipt_id: str,
        observed_at: datetime,
    ) -> UserRelation:
        content_key = build_content_key(Platform.BILIBILI, item.bvid)
        relation_key = build_relation_key(
            account_ref_hash,
            content_key,
            RelationType.SAVED_CURRENT,
            owner_selection_id,
        )
        row = connection.execute(
            "SELECT payload_json FROM user_relation WHERE relation_key = ?",
            (relation_key,),
        ).fetchone()
        first = observed_at
        if row is not None:
            stored = UserRelation.model_validate_json(row["payload_json"])
            if observed_at < stored.last_seen_at:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Bilibili relation time moved backwards")
            first = stored.first_seen_at
        return UserRelation(
            schema_version="1.0",
            relation_key=relation_key,
            account_ref_hash=account_ref_hash,
            content_key=content_key,
            relation_type=RelationType.SAVED_CURRENT,
            source_collection_id=owner_selection_id,
            source_collection_name_private=None,
            first_seen_at=first,
            last_seen_at=observed_at,
            status=RelationStatus.ACTIVE,
            confirmed_by=ConfirmationSource.OWNER,
            scan_receipt_id=scan_receipt_id,
        )

    @staticmethod
    def _observation(
        item: BilibiliSelectedItem,
        *,
        scan_id: str,
        run_id: str,
        observed_at: datetime,
    ) -> SourceObservation:
        facts_hash = _sha256(item.facts())
        observation_id = f"obs_{uuid.uuid5(_scan_uuid(scan_id), f'bili-selected:{facts_hash}').hex}"
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
            content_key=build_content_key(Platform.BILIBILI, item.bvid),
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
                    source=FieldSource.ADAPTER,
                    status=FieldStatus.PRESENT,
                    confidence=1.0,
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
                    status=FieldStatus.PRESENT if item.published_at else FieldStatus.UNKNOWN,
                    confidence=1.0 if item.published_at else 0.0,
                ),
            ),
            completeness=1.0 if item.published_at else 0.8,
            warning_codes=(),
            ephemeral_media_ref_ids=(),
            run_id=run_id,
        )

    def commit_batch(self, scan_id: str, batch: BilibiliSelectedBatch) -> BilibiliSelectedReceipt:
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
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Bilibili scan is not initialized")
            cursor = self._cursor(checkpoint["cursor_value_private"])
            self._validate_graph_state(str(run["state"]), str(checkpoint["state"]), cursor)
            if (
                batch.owner_selection_id != cursor["owner_selection_id"]
                or batch.selection_manifest_sha256 != cursor["selection_manifest_sha256"]
            ):
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Bilibili batch selection conflicts")
            if cursor["last_sequence"] == batch.sequence and cursor["last_batch_hash"] == batch_hash:
                return self._receipt(connection, scan_id, checkpoint, disposition="replayed")
            if checkpoint["state"] != "active" or run["state"] != "running":
                raise X2NRuntimeError(
                    ErrorCode.DATA_INTEGRITY_FAILED, "Bilibili completed scan cannot accept another batch"
                )
            if batch.sequence != cursor["next_sequence"]:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Bilibili batch is not the checkpoint successor")
            if timestamp < str(checkpoint["updated_at"]):
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Bilibili checkpoint time moved backwards")

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
                        owner_selection_id=batch.owner_selection_id,
                        scan_receipt_id=identity["scan_receipt_id"],
                        observed_at=observed_at,
                    )
                    if (
                        self.store._upsert_relation(connection, relation, Platform.BILIBILI.value, timestamp)
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

            killed = batch.status in {"auth_required", "policy_blocked", "captcha_required"}
            state = "complete" if batch.status == "ready" else "invalidated" if killed else "active"
            cursor_kind = (
                "bounded_selection_complete"
                if batch.status == "ready"
                else "platform_policy_killed"
                if killed
                else "owner_selection_blocked"
            )
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
                }
            )
            last_stable = batch.items[-1].bvid if batch.status == "ready" else checkpoint["last_stable_content_id"]
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
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Bilibili checkpoint transition conflicted")
            if state == "complete":
                run_update = connection.execute(
                    "UPDATE run_record SET state = 'succeeded', finished_at = ? WHERE run_id = ? AND state = 'running'",
                    (timestamp, identity["run_id"]),
                )
                if run_update.rowcount != 1:
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Bilibili Run completion conflicted")
            elif state == "invalidated":
                run_update = connection.execute(
                    "UPDATE run_record SET state = 'cancelled', finished_at = ? WHERE run_id = ? AND state = 'running'",
                    (timestamp, identity["run_id"]),
                )
                if run_update.rowcount != 1:
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Bilibili platform Kill conflicted")
            self._fault("after_checkpoint")
            refreshed = connection.execute(
                "SELECT * FROM checkpoint WHERE checkpoint_id = ?",
                (identity["checkpoint_id"],),
            ).fetchone()
            if refreshed is None:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Bilibili checkpoint disappeared")
            expected_writes = len(batch.items) if batch.status == "ready" else 0
            if any(value > expected_writes for value in (content_writes, relation_writes, observation_writes)):
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Bilibili write cardinality is invalid")
            return self._receipt(connection, scan_id, refreshed, disposition="applied")

    def checkpoint(self, scan_id: str) -> BilibiliSelectedReceipt:
        identity = _identity(scan_id)
        with self.store._file_lock(exclusive=False):
            connection = self.store._open(writable=False)
            try:
                checkpoint = connection.execute(
                    "SELECT * FROM checkpoint WHERE checkpoint_id = ?",
                    (identity["checkpoint_id"],),
                ).fetchone()
                if checkpoint is None:
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Bilibili checkpoint is unavailable")
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
    ) -> BilibiliSelectedReceipt:
        identity = _identity(scan_id)
        cursor = self._cursor(checkpoint["cursor_value_private"])
        run = connection.execute("SELECT state FROM run_record WHERE run_id = ?", (identity["run_id"],)).fetchone()
        if run is None:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Bilibili Run is unavailable")
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
        return BilibiliSelectedReceipt(
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
        )


class BilibiliSelectedBatchCoordinator:
    """Apply the single owner action under the global non-waiting Adapter guard."""

    def __init__(self, adapter: BilibiliSelectedAdapter, guard: AdapterExecutionGate) -> None:
        self.adapter = adapter
        self.guard = guard

    def apply_owner_action(
        self,
        scan_id: str,
        batch: BilibiliSelectedBatch,
        *,
        monotonic_batch_time: float,
        monotonic_observation_time: float,
    ) -> BilibiliSelectedReceipt:
        with self.guard.acquire(Platform.BILIBILI.value, now=monotonic_batch_time) as lease:
            lease.permit_item_observation(now=monotonic_observation_time)
            return self.adapter.commit_batch(scan_id, batch)
