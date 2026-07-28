"""Clean-room Xiaohongshu likes batches backed by the Canonical Store.

The module consumes only sanitized facts from one explicit, bounded Chrome
observation. It never opens a platform URL, scrolls, reads browser state, retries,
or decides that an unknown/empty/partial response is a complete scan.
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


TASK_ID = "TSK.x2n.adapters.003"
ADAPTER_NAME = "xhs_likes"
ADAPTER_VERSION = "1.0.0"
RESUME_COMPATIBILITY_VERSION = "xhs-likes-1.1.0"
RUN_KIND = "xhs_likes_scan_v1"
MAX_BATCH_ITEMS = 20
MAX_SCAN_RELATIONS = 10_000
CANARY_ITEM_LIMIT = 20
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SAFE_RELATION_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,767}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
EXTENSION_ERROR_CODES = {
    ErrorCode.ADAPTER_AUTH_EXPIRED.value,
    ErrorCode.PLATFORM_CHANGED.value,
    ErrorCode.POLICY_BLOCKED.value,
    ErrorCode.PROVENANCE_INCOMPLETE.value,
}
BatchStatus = Literal[
    "ready",
    "partial",
    "auth_required",
    "verification_required",
    "platform_changed",
    "empty_unverified",
]
CompletionSignal = Literal["more_available", "unknown", "bounded_limit_reached", "authoritative_end"]
ScopeMode = Literal["canary_20", "full_scan"]
FaultInjector = Callable[[str], None]


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _scan_uuid(value: str) -> uuid.UUID:
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, TypeError, ValueError):
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Likes scan identity is invalid") from None
    if str(parsed) != value:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Likes scan identity is not canonical")
    return parsed


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Likes observation time requires a timezone")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _timestamp(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _safe_optional_text(value: str | None, *, label: str) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 500
        or re.search(r"[\x00-\x1f\x7f]", value)
        or re.search(r"https?://", value, flags=re.IGNORECASE)
    ):
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, f"Likes {label} is unsafe")
    return value


def _identity(scan_id: str) -> dict[str, str]:
    parsed = _scan_uuid(scan_id)
    suffix = parsed.hex
    return {
        "checkpoint_id": f"checkpoint_xhslike_{suffix}",
        "run_id": f"run_xhslike_{suffix}",
        "scan_receipt_id": f"receipt_xhslike_{suffix}",
    }


def _canonical_page_url(content_id: str) -> str:
    return f"https://www.xiaohongshu.com/explore/{content_id}"


@dataclass(frozen=True)
class XhsLikeItem:
    content_id: str
    content_type: Literal["image_gallery", "unknown", "video"]
    title: str | None
    inbox_disposition: Literal["unclassified"] = "unclassified"

    def __post_init__(self) -> None:
        if not isinstance(self.content_id, str) or SAFE_ID.fullmatch(self.content_id) is None:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Likes content identity is invalid")
        if self.content_type not in {"image_gallery", "unknown", "video"}:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Likes content type is invalid")
        _safe_optional_text(self.title, label="title")
        if self.inbox_disposition != "unclassified":
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Likes must enter the conservative Inbox")

    def facts(self) -> dict[str, Any]:
        return {
            "content_id": self.content_id,
            "content_type": self.content_type,
            "inbox_disposition": self.inbox_disposition,
            "page_url": _canonical_page_url(self.content_id),
            "title": self.title,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "XhsLikeItem":
        expected = {
            "content_id",
            "content_type",
            "inbox_disposition",
            "page_url",
            "title",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise X2NRuntimeError(ErrorCode.UNKNOWN_FIELD, "Likes item shape is invalid")
        item = cls(
            content_id=value["content_id"],
            content_type=value["content_type"],
            title=value["title"],
            inbox_disposition=value["inbox_disposition"],
        )
        if value["page_url"] != _canonical_page_url(item.content_id):
            raise X2NRuntimeError(ErrorCode.URL_REJECTED, "Likes page address is not canonical")
        return item


@dataclass(frozen=True)
class XhsLikesBatch:
    sequence: int
    status: BatchStatus
    completion_signal: CompletionSignal
    visible_card_count: int
    items: tuple[XhsLikeItem, ...]
    error_codes: tuple[str, ...]
    observed_at: datetime
    explicit_owner_action: Literal[True] = True
    automatic_scroll: Literal[False] = False

    def __post_init__(self) -> None:
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence < 0:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Likes batch sequence is invalid")
        if self.status not in {
            "ready",
            "partial",
            "auth_required",
            "verification_required",
            "platform_changed",
            "empty_unverified",
        }:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Likes batch status is invalid")
        if self.completion_signal not in {
            "more_available",
            "unknown",
            "bounded_limit_reached",
            "authoritative_end",
        }:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Likes completion signal is invalid")
        if self.explicit_owner_action is not True or self.automatic_scroll is not False:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Likes batch requires an explicit no-scroll action")
        if (
            not isinstance(self.visible_card_count, int)
            or isinstance(self.visible_card_count, bool)
            or not 0 <= self.visible_card_count <= MAX_BATCH_ITEMS
            or len(self.items) > MAX_BATCH_ITEMS
        ):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Likes batch boundary is invalid")
        if len({item.content_id for item in self.items}) != len(self.items):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Likes batch contains duplicate logical items")
        allowed_errors = {item.value for item in ErrorCode}
        if any(code not in allowed_errors for code in self.error_codes):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Likes error evidence is invalid")
        if self.status == "ready":
            if self.error_codes or not self.items or len(self.items) != self.visible_card_count:
                raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Likes ready batch is incomplete")
        elif self.status == "partial":
            if not self.error_codes or len(self.items) + len(self.error_codes) != self.visible_card_count:
                raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Likes partial batch lacks evidence")
        elif self.items or not self.error_codes:
            raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Likes blocked batch is inconsistent")
        if self.status != "ready" and self.completion_signal != "unknown":
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "A non-authoritative batch cannot complete a scan")
        _utc(self.observed_at)

    def batch_hash(self) -> str:
        return _sha256(
            {
                "automatic_scroll": self.automatic_scroll,
                "completion_signal": self.completion_signal,
                "error_codes": self.error_codes,
                "explicit_owner_action": self.explicit_owner_action,
                "items": [item.facts() for item in self.items],
                "observed_at": _timestamp(self.observed_at),
                "sequence": self.sequence,
                "status": self.status,
                "visible_card_count": self.visible_card_count,
            }
        )

    @classmethod
    def from_extension_result(
        cls,
        value: Mapping[str, Any],
        *,
        sequence: int,
        observed_at: datetime,
    ) -> "XhsLikesBatch":
        expected = {"batch", "code", "errors", "inbox", "items", "platform", "schema_version", "status"}
        if not isinstance(value, Mapping) or set(value) != expected:
            raise X2NRuntimeError(ErrorCode.UNKNOWN_FIELD, "Likes extension result shape is invalid")
        if value.get("platform") != "xiaohongshu" or value.get("schema_version") != "1.0":
            raise X2NRuntimeError(ErrorCode.INVALID_SCHEMA_VERSION, "Likes extension result identity is invalid")
        batch = value.get("batch")
        if not isinstance(batch, Mapping) or set(batch) != {
            "automatic_scroll",
            "completion_signal",
            "explicit_owner_action",
            "visible_card_count",
        }:
            raise X2NRuntimeError(ErrorCode.UNKNOWN_FIELD, "Likes extension batch shape is invalid")
        visible_card_count = batch["visible_card_count"]
        if (
            not isinstance(visible_card_count, int)
            or isinstance(visible_card_count, bool)
            or not 0 <= visible_card_count <= MAX_BATCH_ITEMS
        ):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Likes extension visible-card count is invalid")
        inbox = value.get("inbox")
        if not isinstance(inbox, Mapping) or dict(inbox) != {
            "automatic_filing": False,
            "disposition": "unclassified",
            "taxonomy_mutation": False,
        }:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Likes extension Inbox policy is invalid")
        errors = value.get("errors")
        if not isinstance(errors, Sequence) or isinstance(errors, (str, bytes)):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Likes extension errors are invalid")
        error_codes: list[str] = []
        card_indices: list[int] = []
        for row in errors:
            if not isinstance(row, Mapping) or set(row) != {"card_index", "code"}:
                raise X2NRuntimeError(ErrorCode.UNKNOWN_FIELD, "Likes error evidence shape is invalid")
            code = row["code"]
            card_index = row["card_index"]
            if code not in EXTENSION_ERROR_CODES:
                raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Likes extension error code is invalid")
            if card_index is not None:
                if (
                    not isinstance(card_index, int)
                    or isinstance(card_index, bool)
                    or not 0 <= card_index < visible_card_count
                ):
                    raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Likes error card index is invalid")
                card_indices.append(card_index)
            error_codes.append(code)
        if len(card_indices) != len(set(card_indices)):
            raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Likes error card indices are not unique")
        top_code = value.get("code")
        if top_code is not None and top_code not in EXTENSION_ERROR_CODES:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Likes extension top-level error code is invalid")
        if value.get("status") == "ready":
            if top_code is not None:
                raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Likes ready result has an error code")
        else:
            if top_code is None or top_code not in error_codes:
                raise X2NRuntimeError(
                    ErrorCode.PROVENANCE_INCOMPLETE,
                    "Likes non-ready result lacks matching top-level error evidence",
                )
            if value.get("status") == "partial":
                if len(card_indices) != len(error_codes):
                    raise X2NRuntimeError(
                        ErrorCode.PROVENANCE_INCOMPLETE,
                        "Likes partial result lacks per-card error evidence",
                    )
            elif visible_card_count != 0 or len(error_codes) != 1 or card_indices:
                raise X2NRuntimeError(
                    ErrorCode.PROVENANCE_INCOMPLETE,
                    "Likes blocked result must contain one surface-level error",
                )
        items = value.get("items")
        if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Likes extension items are invalid")
        return cls(
            sequence=sequence,
            status=value["status"],
            completion_signal=batch["completion_signal"],
            visible_card_count=visible_card_count,
            items=tuple(XhsLikeItem.from_mapping(item) for item in items),
            error_codes=tuple(error_codes),
            observed_at=observed_at,
            explicit_owner_action=batch["explicit_owner_action"],
            automatic_scroll=batch["automatic_scroll"],
        )


@dataclass(frozen=True)
class XhsLikesReceipt:
    scan_ref_sha256: str
    disposition: Literal["applied", "replayed"]
    checkpoint_state: Literal["active", "complete"]
    cursor_kind: str
    next_sequence: int
    observed_unique_items: int
    relation_count: int
    observation_count: int
    error_evidence_count: int
    full_scan_completed: bool

    def safe_dict(self) -> dict[str, Any]:
        return {
            "adapter": {"name": ADAPTER_NAME, "version": ADAPTER_VERSION},
            "automatic_scrolls": 0,
            "checkpoint": {
                "cursor_kind": self.cursor_kind,
                "next_sequence": self.next_sequence,
                "state": self.checkpoint_state,
            },
            "content_auto_deletes": 0,
            "automatic_classification_writes": 0,
            "disposition": self.disposition,
            "error_evidence_count": self.error_evidence_count,
            "full_scan_completed": self.full_scan_completed,
            "network_calls": 0,
            "observations": self.observation_count,
            "observed_unique_items": self.observed_unique_items,
            "physical_deletes": 0,
            "private_path_emitted": False,
            "relations": self.relation_count,
            "removed_relations": 0,
            "scan_ref_sha256": self.scan_ref_sha256,
            "schema_version": "1.0",
            "taxonomy_mutations": 0,
            "task_id": TASK_ID,
        }


def build_xhs_likes_canary_plan(max_items: int = CANARY_ITEM_LIMIT) -> dict[str, Any]:
    if max_items != CANARY_ITEM_LIMIT:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "The Xiaohongshu Canary is fixed to 20 items")
    return {
        "acceptance_id": "ACC.x2n.xhs.002",
        "adapter": ADAPTER_NAME,
        "automatic_scroll": False,
        "automatic_filing": False,
        "default_inbox_disposition": "unclassified",
        "execution": "NOT_RUN",
        "feature_flag": "xhs_likes",
        "max_items": CANARY_ITEM_LIMIT,
        "network_transport": "NONE_VISIBLE_DOM_ONLY",
        "owner_authorization_required": True,
        "preconditions": [
            "dedicated_profile_healthy",
            "owner_explicit_action",
            "private_gold_manifest_ready",
            "stop_control_visible",
            "policy_recheck_current",
        ],
        "production_enabled": False,
        "real_account_execution": "NOT_RUN",
        "rollback": "disable_xhs_likes_keep_current_page",
        "taxonomy_mutation": False,
        "task_id": TASK_ID,
    }


class XhsLikesAdapter:
    """Atomic batch/checkpoint coordinator over a pre-existing Canonical Store."""

    def __init__(self, store: CanonicalStore, *, fault_injector: FaultInjector | None = None) -> None:
        self.store = store
        self._fault_injector = fault_injector

    def _fault(self, label: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector(label)

    @staticmethod
    def _initial_cursor(scope_mode: ScopeMode) -> dict[str, Any]:
        return {
            "error_evidence_count": 0,
            "last_batch_hash": None,
            "last_error_codes": [],
            "last_outcome": "not_started",
            "last_sequence": None,
            "next_sequence": 0,
            "owner_removed_observed_relation_keys": [],
            "scope_mode": scope_mode,
        }

    @staticmethod
    def _cursor(raw: str | None) -> dict[str, Any]:
        try:
            value = json.loads(raw or "")
        except json.JSONDecodeError:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Likes checkpoint cursor is invalid") from None
        expected = {
            "error_evidence_count",
            "last_batch_hash",
            "last_error_codes",
            "last_outcome",
            "last_sequence",
            "next_sequence",
            "owner_removed_observed_relation_keys",
            "scope_mode",
        }
        removed_keys = value.get("owner_removed_observed_relation_keys") if isinstance(value, dict) else None
        if (
            not isinstance(value, dict)
            or set(value) != expected
            or value["scope_mode"] not in {"canary_20", "full_scan"}
            or not isinstance(value["next_sequence"], int)
            or value["next_sequence"] < 0
            or not isinstance(value["error_evidence_count"], int)
            or value["error_evidence_count"] < 0
            or not isinstance(value["last_error_codes"], list)
            or any(code not in {item.value for item in ErrorCode} for code in value["last_error_codes"])
            or (value["last_sequence"] is not None and not isinstance(value["last_sequence"], int))
            or (value["last_batch_hash"] is not None and SHA256.fullmatch(value["last_batch_hash"]) is None)
            or not isinstance(removed_keys, list)
            or len(removed_keys) > MAX_SCAN_RELATIONS
            or any(not isinstance(key, str) or SAFE_RELATION_KEY.fullmatch(key) is None for key in removed_keys)
            or removed_keys != sorted(set(removed_keys))
        ):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Likes checkpoint cursor is invalid")
        return value

    def begin_scan(
        self,
        scan_id: str,
        *,
        account_ref_hash: str,
        scope_mode: ScopeMode,
        started_at: datetime,
    ) -> XhsLikesReceipt:
        identity = _identity(scan_id)
        if SHA256.fullmatch(account_ref_hash) is None:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Likes account reference is invalid")
        if scope_mode not in {"canary_20", "full_scan"}:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Likes scan scope is invalid")
        timestamp = _timestamp(started_at)
        input_hash = _sha256({"account_ref_hash": account_ref_hash, "scope_mode": scope_mode})
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
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Likes scan graph is incomplete")
            if run is None:
                connection.execute(
                    "INSERT OR IGNORE INTO account_ref(account_ref_hash, platform, created_at) VALUES (?, ?, ?)",
                    (account_ref_hash, Platform.XIAOHONGSHU.value, timestamp),
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
                    ) VALUES (?, ?, ?, ?, 'liked', 'owner_bounded_batch', ?, NULL, NULL, 0, 0.0, ?, 'active', ?, ?)
                    """,
                    (
                        identity["checkpoint_id"],
                        ADAPTER_NAME,
                        ADAPTER_VERSION,
                        account_ref_hash,
                        _canonical_json(self._initial_cursor(scope_mode)),
                        RESUME_COMPATIBILITY_VERSION,
                        timestamp,
                        timestamp,
                    ),
                )
                checkpoint = connection.execute(
                    "SELECT * FROM checkpoint WHERE checkpoint_id = ?",
                    (identity["checkpoint_id"],),
                ).fetchone()
            else:
                if (
                    run["run_kind"] != RUN_KIND
                    or run["input_manifest_hash"] != input_hash
                    or checkpoint["adapter_name"] != ADAPTER_NAME
                    or checkpoint["adapter_version"] != ADAPTER_VERSION
                    or checkpoint["account_ref_hash"] != account_ref_hash
                    or checkpoint["resume_compatibility_version"] != RESUME_COMPATIBILITY_VERSION
                ):
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Likes scan identity conflicts")
                cursor = self._cursor(checkpoint["cursor_value_private"])
                if cursor["scope_mode"] != scope_mode:
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Likes scan scope conflicts")
            assert checkpoint is not None
            return self._receipt(connection, scan_id, checkpoint, disposition="replayed" if run else "applied")

    @staticmethod
    def _content(
        connection: Any,
        item: XhsLikeItem,
        observed_at: datetime,
    ) -> CanonicalContent:
        content_key = build_content_key(Platform.XIAOHONGSHU, item.content_id)
        row = connection.execute(
            "SELECT payload_json FROM content WHERE content_key = ?",
            (content_key,),
        ).fetchone()
        first = observed_at
        version = 1
        if row is not None:
            stored = CanonicalContent.model_validate_json(row["payload_json"])
            if observed_at < stored.last_observed_at:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Likes content time moved backwards")
            first = stored.first_observed_at
            version = stored.record_version if observed_at == stored.last_observed_at else stored.record_version + 1
        return CanonicalContent(
            schema_version="1.0",
            content_key=content_key,
            platform=Platform.XIAOHONGSHU,
            platform_content_id=item.content_id,
            canonical_source_url=_canonical_page_url(item.content_id),
            content_type=ContentType(item.content_type),
            title=item.title,
            description=None,
            author_name=None,
            author_platform_id=None,
            published_at=None,
            content_hash=_sha256(
                {"content_id": item.content_id, "content_type": item.content_type, "title": item.title}
            ),
            first_observed_at=first,
            last_observed_at=observed_at,
            record_version=version,
            status=ContentStatus.ACTIVE,
        )

    @staticmethod
    def _relation(
        connection: Any,
        item: XhsLikeItem,
        *,
        account_ref_hash: str,
        scan_receipt_id: str,
        observed_at: datetime,
    ) -> UserRelation:
        content_key = build_content_key(Platform.XIAOHONGSHU, item.content_id)
        relation_key = build_relation_key(
            account_ref_hash,
            content_key,
            RelationType.LIKED,
        )
        row = connection.execute(
            "SELECT payload_json FROM user_relation WHERE relation_key = ?",
            (relation_key,),
        ).fetchone()
        first = observed_at
        if row is not None:
            stored = UserRelation.model_validate_json(row["payload_json"])
            if observed_at < stored.last_seen_at:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Likes relation time moved backwards")
            first = stored.first_seen_at
        return UserRelation(
            schema_version="1.0",
            relation_key=relation_key,
            account_ref_hash=account_ref_hash,
            content_key=content_key,
            relation_type=RelationType.LIKED,
            source_collection_id=None,
            source_collection_name_private=None,
            first_seen_at=first,
            last_seen_at=observed_at,
            status=RelationStatus.ACTIVE,
            confirmed_by=ConfirmationSource.SCAN,
            scan_receipt_id=scan_receipt_id,
        )

    @staticmethod
    def _observation(item: XhsLikeItem, *, scan_id: str, run_id: str, observed_at: datetime) -> SourceObservation:
        parsed = _scan_uuid(scan_id)
        facts_hash = _sha256(item.facts())
        observation_id = f"obs_{uuid.uuid5(parsed, f'xhs-like:{facts_hash}:{_timestamp(observed_at)}').hex}"
        fields = (
            CanonicalField.PLATFORM_CONTENT_ID,
            CanonicalField.CANONICAL_SOURCE_URL,
            CanonicalField.CONTENT_TYPE,
            CanonicalField.TITLE,
        )
        return SourceObservation(
            schema_version="1.0",
            observation_id=observation_id,
            content_key=build_content_key(Platform.XIAOHONGSHU, item.content_id),
            adapter_name=ADAPTER_NAME,
            adapter_version=ADAPTER_VERSION,
            source_method=SourceMethod.SELECTED_COLLECTION,
            observed_at=observed_at,
            raw_text_hash=facts_hash,
            normalized_fields=fields,
            field_provenance=(
                FieldProvenance(
                    field=CanonicalField.PLATFORM_CONTENT_ID,
                    source=FieldSource.DOM,
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
                    source=FieldSource.DOM,
                    status=FieldStatus.UNKNOWN if item.content_type == "unknown" else FieldStatus.PRESENT,
                    confidence=0.5 if item.content_type == "unknown" else 1.0,
                ),
                FieldProvenance(
                    field=CanonicalField.TITLE,
                    source=FieldSource.DOM,
                    status=FieldStatus.UNKNOWN if item.title is None else FieldStatus.PRESENT,
                    confidence=0.0 if item.title is None else 1.0,
                ),
            ),
            completeness=sum((1, 1, int(item.content_type != "unknown"), int(item.title is not None))) / 4,
            warning_codes=(),
            ephemeral_media_ref_ids=(),
            run_id=run_id,
        )

    def commit_batch(self, scan_id: str, batch: XhsLikesBatch) -> XhsLikesReceipt:
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
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Likes scan is not initialized")
            if timestamp < str(checkpoint["updated_at"]):
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Likes checkpoint time moved backwards")
            cursor = self._cursor(checkpoint["cursor_value_private"])
            if cursor["last_sequence"] == batch.sequence and cursor["last_batch_hash"] == batch_hash:
                return self._receipt(connection, scan_id, checkpoint, disposition="replayed")
            if batch.sequence < cursor["next_sequence"] or checkpoint["state"] == "complete":
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Likes replay does not match checkpoint")
            if batch.sequence != cursor["next_sequence"]:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Likes batch is not the checkpoint successor")

            account_ref_hash = str(checkpoint["account_ref_hash"])
            content_writes = relation_writes = observation_writes = 0
            owner_removed_observed = set(cursor["owner_removed_observed_relation_keys"])
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
                    self.store._upsert_relation(connection, relation, Platform.XIAOHONGSHU.value, timestamp)
                    is not WriteDisposition.UNCHANGED
                ):
                    relation_writes += 1
                stored_relation = connection.execute(
                    "SELECT status, confirmed_by FROM user_relation WHERE relation_key = ?",
                    (relation.relation_key,),
                ).fetchone()
                if (
                    stored_relation is not None
                    and str(stored_relation["status"]) == RelationStatus.REMOVED.value
                    and str(stored_relation["confirmed_by"]) == ConfirmationSource.OWNER.value
                ):
                    owner_removed_observed.add(relation.relation_key)
                    if len(owner_removed_observed) > MAX_SCAN_RELATIONS:
                        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Likes scan relation bound exceeded")
                observation = self._observation(
                    item,
                    scan_id=scan_id,
                    run_id=identity["run_id"],
                    observed_at=observed_at,
                )
                if self.store._append_observation(connection, observation, timestamp) is not WriteDisposition.UNCHANGED:
                    observation_writes += 1
                self._fault(f"after_item_{index}")

            observed_count = int(
                connection.execute(
                    "SELECT COUNT(DISTINCT content_key) FROM source_observation WHERE run_id = ?",
                    (identity["run_id"],),
                ).fetchone()[0]
            )
            if batch.completion_signal == "bounded_limit_reached":
                if cursor["scope_mode"] != "canary_20" or observed_count != CANARY_ITEM_LIMIT:
                    raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Likes bounded Canary completion is invalid")
                state = "complete"
                cursor_kind = "bounded_scope_complete"
                confidence = 1.0
                full_scan_id = None
            elif batch.completion_signal == "authoritative_end":
                if cursor["scope_mode"] != "full_scan":
                    raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Likes full-scan completion scope is invalid")
                state = "complete"
                cursor_kind = "authoritative_visible_end"
                confidence = 1.0
                full_scan_id = identity["run_id"]
            else:
                state = "active"
                cursor_kind = "owner_bounded_batch"
                confidence = 0.0
                full_scan_id = None

            advances = batch.status == "ready"
            next_sequence = batch.sequence + 1 if advances else batch.sequence
            cursor.update(
                {
                    "error_evidence_count": cursor["error_evidence_count"] + len(batch.error_codes),
                    "last_batch_hash": batch_hash,
                    "last_error_codes": list(batch.error_codes),
                    "last_outcome": batch.status,
                    "last_sequence": batch.sequence,
                    "next_sequence": next_sequence,
                    "owner_removed_observed_relation_keys": sorted(owner_removed_observed),
                }
            )
            if batch.status != "ready":
                state = "active"
                cursor_kind = "owner_bounded_batch"
                confidence = 0.0
                full_scan_id = None
            last_stable = batch.items[-1].content_id if batch.items else checkpoint["last_stable_content_id"]
            self._fault("before_checkpoint")
            updated = connection.execute(
                """
                UPDATE checkpoint SET
                    cursor_kind = ?, cursor_value_private = ?, last_stable_content_id = ?, full_scan_id = ?,
                    observed_count = ?, completion_confidence = ?, state = ?, updated_at = ?
                WHERE checkpoint_id = ? AND state = 'active'
                """,
                (
                    cursor_kind,
                    _canonical_json(cursor),
                    last_stable,
                    full_scan_id,
                    observed_count,
                    confidence,
                    state,
                    timestamp,
                    identity["checkpoint_id"],
                ),
            )
            if updated.rowcount != 1:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Likes checkpoint transition conflicted")
            if state == "complete":
                run_update = connection.execute(
                    "UPDATE run_record SET state = 'succeeded', finished_at = ? WHERE run_id = ? AND state = 'running'",
                    (timestamp, identity["run_id"]),
                )
                if run_update.rowcount != 1:
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Likes Run transition conflicted")
            self._fault("after_checkpoint")
            refreshed = connection.execute(
                "SELECT * FROM checkpoint WHERE checkpoint_id = ?",
                (identity["checkpoint_id"],),
            ).fetchone()
            if refreshed is None:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Likes checkpoint disappeared")
            receipt = self._receipt(connection, scan_id, refreshed, disposition="applied")
            expected_writes = len(batch.items)
            if (
                observation_writes > expected_writes
                or relation_writes > expected_writes
                or content_writes > expected_writes
            ):
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Likes write cardinality is invalid")
            return receipt

    def checkpoint(self, scan_id: str) -> XhsLikesReceipt:
        identity = _identity(scan_id)
        with self.store._file_lock(exclusive=False):
            connection = self.store._open(writable=False)
            try:
                checkpoint = connection.execute(
                    "SELECT * FROM checkpoint WHERE checkpoint_id = ?",
                    (identity["checkpoint_id"],),
                ).fetchone()
                if checkpoint is None:
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Likes checkpoint is unavailable")
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
    ) -> XhsLikesReceipt:
        identity = _identity(scan_id)
        cursor = self._cursor(checkpoint["cursor_value_private"])
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
        return XhsLikesReceipt(
            scan_ref_sha256=hashlib.sha256(scan_id.encode("ascii")).hexdigest(),
            disposition=disposition,
            checkpoint_state=checkpoint["state"],
            cursor_kind=checkpoint["cursor_kind"],
            next_sequence=cursor["next_sequence"],
            observed_unique_items=int(checkpoint["observed_count"]),
            relation_count=relation_count,
            observation_count=observation_count,
            error_evidence_count=cursor["error_evidence_count"],
            full_scan_completed=checkpoint["full_scan_id"] is not None,
        )


class XhsLikesBatchCoordinator:
    """Apply one user action under the global non-waiting Adapter guard."""

    def __init__(self, adapter: XhsLikesAdapter, guard: AdapterExecutionGate) -> None:
        self.adapter = adapter
        self.guard = guard

    def apply_owner_action(
        self,
        scan_id: str,
        batch: XhsLikesBatch,
        *,
        monotonic_batch_time: float,
        monotonic_observation_time: float,
    ) -> XhsLikesReceipt:
        with self.guard.acquire(Platform.XIAOHONGSHU.value, now=monotonic_batch_time) as lease:
            lease.permit_item_observation(now=monotonic_observation_time)
            return self.adapter.commit_batch(scan_id, batch)


def synthetic_started_at() -> datetime:
    """Stable helper for public CI fixtures; production callers must pass live UTC."""

    return datetime(2026, 1, 1, tzinfo=timezone.utc)
