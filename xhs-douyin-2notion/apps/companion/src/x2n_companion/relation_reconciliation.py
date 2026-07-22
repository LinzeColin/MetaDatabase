"""Durable fail-closed relation reconciliation for authoritative full scans.

The reconciler never fetches platform data and never physically deletes a
relation or Content row.  It consumes an already committed source checkpoint,
proves that the checkpoint represents an authoritative complete XHS scan, and
then applies the conservative state machine:

``active -> unknown -> tombstone_candidate``.

Only an Owner-confirmed downstream workflow may ever move a candidate to
``removed``.  Empty, partial, auth, HTTP, or platform-change outcomes clear the
consecutive-missing chain without changing a relation.
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

from x2n_contracts import ErrorCode, UserRelation
from x2n_contracts.models import ConfirmationSource, Platform, RelationStatus, RelationType

from .canonical_store import CanonicalStore, WriteDisposition
from .runtime import X2NRuntimeError


TASK_ID = "TSK.x2n.adapters.005"
ADAPTER_NAME = "relation_reconciliation"
ADAPTER_VERSION = "1.0.0"
RESUME_COMPATIBILITY_VERSION = "relation-reconciliation-1.0.0"
RUN_KIND = "relation_reconciliation_v1"
POLICY_REVISION = "2026-07-23"
OWNER_ALPHA_ITEM_LIMIT = 80
MAX_SCOPE_RELATIONS = 10_000

SHA256 = re.compile(r"^[0-9a-f]{64}$")
SAFE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,767}$")
Outcome = Literal[
    "auth_expired",
    "http_error",
    "platform_changed",
    "empty_response",
    "partial_scan",
    "complete_success",
]
NON_AUTHORITATIVE_OUTCOMES = {
    "auth_expired",
    "http_error",
    "platform_changed",
    "empty_response",
    "partial_scan",
}
FaultInjector = Callable[[str], None]


@dataclass(frozen=True)
class SourceRule:
    platform: Platform
    relation_types: tuple[RelationType, ...]
    authoritative_full_scan: bool
    source_run_kind: str | None = None
    run_prefix: str | None = None
    receipt_prefix: str | None = None
    source_observation_method: str | None = None


SOURCE_RULES = {
    "xhs_favorites": SourceRule(
        Platform.XIAOHONGSHU,
        (RelationType.FAVORITED,),
        True,
        "xhs_favorites_scan_v1",
        "run_xhsfav_",
        "receipt_xhsfav_",
        "selected_collection",
    ),
    "xhs_likes": SourceRule(
        Platform.XIAOHONGSHU,
        (RelationType.LIKED,),
        True,
        "xhs_likes_scan_v1",
        "run_xhslike_",
        "receipt_xhslike_",
        "selected_collection",
    ),
    "douyin_upstream": SourceRule(
        Platform.DOUYIN,
        (RelationType.FAVORITED, RelationType.LIKED),
        False,
    ),
    "bilibili_selected_collection": SourceRule(
        Platform.BILIBILI,
        (RelationType.SAVED_CURRENT,),
        False,
    ),
    "kuaishou_selected_collection": SourceRule(
        Platform.KUAISHOU,
        (RelationType.SAVED_CURRENT,),
        False,
    ),
    "weibo_selected_collection": SourceRule(
        Platform.WEIBO,
        (RelationType.FAVORITED,),
        False,
    ),
    "taobao_selected_collection": SourceRule(
        Platform.TAOBAO,
        (RelationType.SAVED_CURRENT,),
        False,
    ),
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Reconciliation time requires an explicit timezone")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _timestamp(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _stored_utc(value: Any, code: ErrorCode, message: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise X2NRuntimeError(code, message)
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError:
        raise X2NRuntimeError(code, message) from None
    if _timestamp(parsed) != value:
        raise X2NRuntimeError(code, message)
    return parsed


def _event_suffix(value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, TypeError, ValueError):
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Reconciliation event identity is invalid") from None
    if str(parsed) != value:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Reconciliation event identity is not canonical")
    return parsed.hex


def _validate_relation_key(value: Any, account_ref_hash: str) -> str:
    if not isinstance(value, str) or SAFE_REF.fullmatch(value) is None or not value.startswith(account_ref_hash + ":"):
        raise X2NRuntimeError(ErrorCode.RELATION_KEY_INVALID, "Reconciliation relation identity is invalid")
    return value


@dataclass(frozen=True)
class ReconciliationManifest:
    event_id: str
    source_adapter: str
    platform: Platform
    account_ref_hash: str
    relation_type: RelationType
    outcome: Outcome
    observed_relation_keys: tuple[str, ...]
    source_checkpoint_id: str | None
    source_scan_receipt_id: str | None
    source_observed_content_count: int
    observed_at: datetime
    policy_revision: Literal["2026-07-23"] = POLICY_REVISION

    def __post_init__(self) -> None:
        _event_suffix(self.event_id)
        if not isinstance(self.source_adapter, str) or self.source_adapter not in SOURCE_RULES:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Reconciliation source adapter is unsupported")
        rule = SOURCE_RULES[self.source_adapter]
        if self.platform is not rule.platform or self.relation_type not in rule.relation_types:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Reconciliation source scope is inconsistent")
        if not isinstance(self.outcome, str) or self.outcome not in NON_AUTHORITATIVE_OUTCOMES | {"complete_success"}:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Reconciliation outcome is unsupported")
        if self.policy_revision != POLICY_REVISION:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Reconciliation policy is stale")
        if not isinstance(self.account_ref_hash, str) or SHA256.fullmatch(self.account_ref_hash) is None:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Reconciliation account reference is invalid")
        if (
            not isinstance(self.source_observed_content_count, int)
            or isinstance(self.source_observed_content_count, bool)
            or not 0 <= self.source_observed_content_count <= MAX_SCOPE_RELATIONS
        ):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Reconciliation observed count is invalid")
        if not isinstance(self.observed_relation_keys, tuple):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Reconciliation relation manifest must be immutable")
        keys = tuple(_validate_relation_key(item, self.account_ref_hash) for item in self.observed_relation_keys)
        if len(keys) > MAX_SCOPE_RELATIONS or len(set(keys)) != len(keys):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Reconciliation relation manifest is invalid")
        _utc(self.observed_at)

        if self.outcome == "complete_success":
            if not rule.authoritative_full_scan:
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Bounded selection cannot claim a full scan")
            if not keys or self.source_observed_content_count < 1:
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "An empty response cannot be authoritative")
            if (
                not isinstance(self.source_checkpoint_id, str)
                or SAFE_REF.fullmatch(self.source_checkpoint_id) is None
                or not isinstance(self.source_scan_receipt_id, str)
                or SAFE_REF.fullmatch(self.source_scan_receipt_id) is None
            ):
                raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Full-scan evidence is incomplete")
        elif (
            keys
            or self.source_checkpoint_id is not None
            or self.source_scan_receipt_id is not None
            or self.source_observed_content_count != 0
        ):
            raise X2NRuntimeError(
                ErrorCode.POLICY_BLOCKED,
                "Non-authoritative outcomes cannot carry full-scan observations",
            )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ReconciliationManifest":
        expected = {
            "account_ref_hash",
            "event_id",
            "observed_at",
            "observed_relation_keys",
            "outcome",
            "platform",
            "policy_revision",
            "relation_type",
            "source_adapter",
            "source_checkpoint_id",
            "source_observed_content_count",
            "source_scan_receipt_id",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise X2NRuntimeError(ErrorCode.UNKNOWN_FIELD, "Reconciliation manifest shape is invalid")
        observed = value["observed_relation_keys"]
        if not isinstance(observed, Sequence) or isinstance(observed, (str, bytes)):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Reconciliation relation manifest is invalid")
        observed_at = value["observed_at"]
        if not isinstance(observed_at, str) or not observed_at.endswith("Z"):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Reconciliation observed_at is invalid")
        try:
            parsed = datetime.fromisoformat(observed_at.removesuffix("Z") + "+00:00")
        except ValueError:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Reconciliation observed_at is invalid") from None
        try:
            platform = Platform(value["platform"])
            relation_type = RelationType(value["relation_type"])
        except (TypeError, ValueError):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Reconciliation enum input is invalid") from None
        return cls(
            event_id=value["event_id"],
            source_adapter=value["source_adapter"],
            platform=platform,
            account_ref_hash=value["account_ref_hash"],
            relation_type=relation_type,
            outcome=value["outcome"],
            observed_relation_keys=tuple(observed),
            source_checkpoint_id=value["source_checkpoint_id"],
            source_scan_receipt_id=value["source_scan_receipt_id"],
            source_observed_content_count=value["source_observed_content_count"],
            observed_at=parsed,
            policy_revision=value["policy_revision"],
        )

    def input_hash(self) -> str:
        return _sha256(
            {
                "account_ref_hash": self.account_ref_hash,
                "event_id": self.event_id,
                "observed_at": _timestamp(self.observed_at),
                "observed_relation_keys": self.observed_relation_keys,
                "outcome": self.outcome,
                "platform": self.platform.value,
                "policy_revision": self.policy_revision,
                "relation_type": self.relation_type.value,
                "source_adapter": self.source_adapter,
                "source_checkpoint_id": self.source_checkpoint_id,
                "source_observed_content_count": self.source_observed_content_count,
                "source_scan_receipt_id": self.source_scan_receipt_id,
            }
        )

    def scope_hash(self) -> str:
        return _sha256(
            {
                "account_ref_hash": self.account_ref_hash,
                "platform": self.platform.value,
                "relation_type": self.relation_type.value,
                "source_adapter": self.source_adapter,
            }
        )


@dataclass(frozen=True)
class ReconciliationReceipt:
    disposition: Literal["applied", "replayed"]
    outcome: Outcome
    scope_ref_sha256: str
    source_full_scan_ref_sha256: str | None
    source_scan_receipt_ref_sha256: str | None
    full_scan_verified: bool
    observed_relation_count: int
    source_observed_content_count: int
    scope_relation_count: int
    missing_relation_count: int
    unknown_transition_count: int
    tombstone_candidate_transition_count: int
    tombstone_candidate_total: int
    reactivated_count: int
    pending_missing_count: int
    removed_preserved_count: int

    def safe_dict(self) -> dict[str, Any]:
        return {
            "adapter": {"name": ADAPTER_NAME, "version": ADAPTER_VERSION},
            "automatic_pagination": 0,
            "automatic_scroll": 0,
            "content_auto_deletes": 0,
            "disposition": self.disposition,
            "full_scan": {
                "observed_content_count": self.source_observed_content_count,
                "source_full_scan_ref_sha256": self.source_full_scan_ref_sha256,
                "source_scan_receipt_ref_sha256": self.source_scan_receipt_ref_sha256,
                "verified": self.full_scan_verified,
            },
            "missing_relation_count": self.missing_relation_count,
            "observed_relation_count": self.observed_relation_count,
            "outcome": self.outcome,
            "owner_alpha": "NOT_RUN",
            "pending_missing_count": self.pending_missing_count,
            "physical_deletes": 0,
            "platform_calls": 0,
            "private_path_emitted": False,
            "reactivated_count": self.reactivated_count,
            "relation_keys_emitted": False,
            "removed_preserved_count": self.removed_preserved_count,
            "removed_writes": 0,
            "scope_ref_sha256": self.scope_ref_sha256,
            "scope_relation_count": self.scope_relation_count,
            "schema_version": "1.0",
            "task_id": TASK_ID,
            "tombstone_candidate_total": self.tombstone_candidate_total,
            "tombstone_candidate_transition_count": self.tombstone_candidate_transition_count,
            "unknown_transition_count": self.unknown_transition_count,
        }


def build_owner_alpha_80_manifest_plan(item_count: int = OWNER_ALPHA_ITEM_LIMIT) -> dict[str, Any]:
    if not isinstance(item_count, int) or isinstance(item_count, bool) or item_count != OWNER_ALPHA_ITEM_LIMIT:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Owner Alpha manifest is fixed to 80 items")
    return {
        "acceptance_id": "ACC.x2n.rel.006",
        "automatic_pagination": False,
        "automatic_scroll": False,
        "execution": "NOT_RUN",
        "item_count": OWNER_ALPHA_ITEM_LIMIT,
        "owner_profile_required": True,
        "physical_delete_enabled": False,
        "platform_calls": 0,
        "private_manifest_required": True,
        "relation_keys_in_plan": 0,
        "scopes": [
            {"count": 20, "platform": "xiaohongshu", "relation": "favorited"},
            {"count": 20, "platform": "xiaohongshu", "relation": "liked"},
            {"count": 20, "platform": "douyin", "relation": "favorited"},
            {"count": 20, "platform": "douyin", "relation": "liked"},
        ],
        "status": "TOOLING_READY_OWNER_ALPHA_NOT_RUN",
        "task_id": TASK_ID,
    }


class RelationReconciler:
    """Reconcile one durable scope without ever committing a removal."""

    def __init__(self, store: CanonicalStore, *, fault_injector: FaultInjector | None = None) -> None:
        self.store = store
        self._fault_injector = fault_injector

    def _fault(self, label: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector(label)

    @staticmethod
    def _identity(manifest: ReconciliationManifest) -> dict[str, str]:
        suffix = _event_suffix(manifest.event_id)
        scope_hash = manifest.scope_hash()
        return {
            "checkpoint_id": f"checkpoint_reconcile_{scope_hash[:32]}",
            "receipt_id": f"receipt_reconcile_{suffix}",
            "run_id": f"run_reconcile_{suffix}",
            "scope_hash": scope_hash,
        }

    @staticmethod
    def _initial_cursor(manifest: ReconciliationManifest) -> dict[str, Any]:
        return {
            "last_event_id": None,
            "last_input_sha256": None,
            "last_observed_at": None,
            "last_outcome": "not_started",
            "last_source_checkpoint_at": None,
            "last_source_full_scan_ref_sha256": None,
            "pending_missing_relation_keys": [],
            "platform": manifest.platform.value,
            "relation_type": manifest.relation_type.value,
            "schema_version": "1.0",
            "scope_ref_sha256": manifest.scope_hash(),
            "source_adapter": manifest.source_adapter,
            "total_complete_scans": 0,
            "total_non_authoritative_events": 0,
        }

    @staticmethod
    def _cursor(raw: Any, manifest: ReconciliationManifest) -> dict[str, Any]:
        try:
            value = json.loads(raw or "")
        except json.JSONDecodeError:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Reconciliation checkpoint is invalid") from None
        expected = {
            "last_event_id",
            "last_input_sha256",
            "last_observed_at",
            "last_outcome",
            "last_source_checkpoint_at",
            "last_source_full_scan_ref_sha256",
            "pending_missing_relation_keys",
            "platform",
            "relation_type",
            "schema_version",
            "scope_ref_sha256",
            "source_adapter",
            "total_complete_scans",
            "total_non_authoritative_events",
        }
        if not isinstance(value, dict) or set(value) != expected:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Reconciliation checkpoint is invalid")
        if (
            value["schema_version"] != "1.0"
            or value["scope_ref_sha256"] != manifest.scope_hash()
            or value["platform"] != manifest.platform.value
            or value["relation_type"] != manifest.relation_type.value
            or value["source_adapter"] != manifest.source_adapter
            or value["last_outcome"] not in NON_AUTHORITATIVE_OUTCOMES | {"not_started", "complete_success"}
        ):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Reconciliation checkpoint scope diverged")
        for field in ("total_complete_scans", "total_non_authoritative_events"):
            if not isinstance(value[field], int) or isinstance(value[field], bool) or value[field] < 0:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Reconciliation checkpoint count is invalid")
        for field in ("last_input_sha256", "last_source_full_scan_ref_sha256"):
            if value[field] is not None and (
                not isinstance(value[field], str) or SHA256.fullmatch(value[field]) is None
            ):
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Reconciliation checkpoint hash is invalid")
        if (value["last_source_checkpoint_at"] is None) != (value["last_source_full_scan_ref_sha256"] is None):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Reconciliation source cursor is incomplete")
        if value["last_event_id"] is not None:
            _event_suffix(value["last_event_id"])
        event_present = value["last_event_id"] is not None
        if not (event_present == (value["last_input_sha256"] is not None) == (value["last_observed_at"] is not None)):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Reconciliation event cursor is incomplete")
        if not event_present:
            if (
                value["last_outcome"] != "not_started"
                or value["total_complete_scans"] != 0
                or value["total_non_authoritative_events"] != 0
                or value["last_source_checkpoint_at"] is not None
                or value["pending_missing_relation_keys"]
            ):
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Reconciliation initial cursor diverged")
        elif (
            value["last_outcome"] == "not_started"
            or value["total_complete_scans"] + value["total_non_authoritative_events"] < 1
            or value["last_outcome"] == "complete_success"
            and value["total_complete_scans"] < 1
            or value["last_outcome"] in NON_AUTHORITATIVE_OUTCOMES
            and value["total_non_authoritative_events"] < 1
        ):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Reconciliation event counters diverged")
        if (value["total_complete_scans"] == 0) != (value["last_source_checkpoint_at"] is None):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Reconciliation source history diverged")
        if value["pending_missing_relation_keys"] and value["last_outcome"] != "complete_success":
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Reconciliation pending chain diverged")
        parsed_times: dict[str, datetime] = {}
        for field in ("last_observed_at", "last_source_checkpoint_at"):
            if value[field] is None:
                continue
            parsed_times[field] = _stored_utc(
                value[field],
                ErrorCode.DATA_INTEGRITY_FAILED,
                "Reconciliation checkpoint time is invalid",
            )
        if (
            "last_source_checkpoint_at" in parsed_times
            and parsed_times["last_source_checkpoint_at"] > parsed_times["last_observed_at"]
        ):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Reconciliation source time diverged")
        pending = value["pending_missing_relation_keys"]
        if not isinstance(pending, list) or len(pending) > MAX_SCOPE_RELATIONS:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Reconciliation pending set is invalid")
        normalized = [_validate_relation_key(item, manifest.account_ref_hash) for item in pending]
        if normalized != sorted(set(normalized)):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Reconciliation pending set is not canonical")
        return value

    @staticmethod
    def _relation_from_row(row: Any) -> UserRelation:
        try:
            relation = UserRelation.model_validate_json(row["payload_json"])
        except ValueError:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Stored relation payload is invalid") from None
        if (
            relation.relation_key != str(row["relation_key"])
            or relation.account_ref_hash != str(row["account_ref_hash"])
            or relation.content_key != str(row["content_key"])
            or relation.relation_type.value != str(row["relation_type"])
            or relation.source_collection_id != row["source_collection_id"]
            or relation.source_collection_name_private != row["source_collection_name_private"]
            or _timestamp(relation.first_seen_at) != str(row["first_seen_at"])
            or _timestamp(relation.last_seen_at) != str(row["last_seen_at"])
            or relation.status.value != str(row["status"])
            or relation.confirmed_by.value != str(row["confirmed_by"])
            or relation.scan_receipt_id != str(row["scan_receipt_id"])
            or _sha256(relation.model_dump(mode="json", by_alias=True)) != str(row["payload_sha256"])
        ):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Stored relation row and payload diverged")
        return relation

    @staticmethod
    def _scope_rows(connection: Any, manifest: ReconciliationManifest) -> list[Any]:
        rows = connection.execute(
            """
            SELECT ur.*, c.platform
            FROM user_relation AS ur
            JOIN content AS c ON c.content_key = ur.content_key
            WHERE ur.account_ref_hash = ? AND ur.relation_type = ?
            ORDER BY ur.relation_key
            LIMIT ?
            """,
            (manifest.account_ref_hash, manifest.relation_type.value, MAX_SCOPE_RELATIONS + 1),
        ).fetchall()
        if len(rows) > MAX_SCOPE_RELATIONS:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Reconciliation scope exceeds the bound")
        if any(str(row["platform"]) != manifest.platform.value for row in rows):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Relation scope crosses platform boundary")
        relations = [RelationReconciler._relation_from_row(row) for row in rows]
        if any(
            relation.status is RelationStatus.REMOVED and relation.confirmed_by is not ConfirmationSource.OWNER
            for relation in relations
        ):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Removed relation lacks Owner confirmation")
        return rows

    def _ensure_scope_checkpoint(
        self,
        connection: Any,
        manifest: ReconciliationManifest,
        identity: Mapping[str, str],
        timestamp: str,
        *,
        create_if_missing: bool = True,
    ) -> tuple[Any, dict[str, Any]]:
        account = connection.execute(
            "SELECT platform FROM account_ref WHERE account_ref_hash = ?",
            (manifest.account_ref_hash,),
        ).fetchone()
        if account is None or str(account["platform"]) != manifest.platform.value:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Reconciliation account scope is unavailable")
        checkpoint = connection.execute(
            "SELECT * FROM checkpoint WHERE checkpoint_id = ?",
            (identity["checkpoint_id"],),
        ).fetchone()
        if checkpoint is None:
            if not create_if_missing:
                raise X2NRuntimeError(
                    ErrorCode.DATA_INTEGRITY_FAILED,
                    "Successful reconciliation Run lost its durable checkpoint",
                )
            cursor = self._initial_cursor(manifest)
            connection.execute(
                """
                INSERT INTO checkpoint(
                    checkpoint_id, adapter_name, adapter_version, account_ref_hash, relation_type,
                    cursor_kind, cursor_value_private, last_stable_content_id, full_scan_id,
                    observed_count, completion_confidence, resume_compatibility_version, state,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'no_authoritative_baseline', ?, NULL, NULL, 0, 0.0, ?, 'active', ?, ?)
                """,
                (
                    identity["checkpoint_id"],
                    ADAPTER_NAME,
                    ADAPTER_VERSION,
                    manifest.account_ref_hash,
                    manifest.relation_type.value,
                    _canonical_json(cursor),
                    RESUME_COMPATIBILITY_VERSION,
                    timestamp,
                    timestamp,
                ),
            )
            checkpoint = connection.execute(
                "SELECT * FROM checkpoint WHERE checkpoint_id = ?",
                (identity["checkpoint_id"],),
            ).fetchone()
        if (
            checkpoint is None
            or str(checkpoint["adapter_name"]) != ADAPTER_NAME
            or str(checkpoint["adapter_version"]) != ADAPTER_VERSION
            or str(checkpoint["account_ref_hash"]) != manifest.account_ref_hash
            or str(checkpoint["relation_type"]) != manifest.relation_type.value
            or str(checkpoint["resume_compatibility_version"]) != RESUME_COMPATIBILITY_VERSION
            or str(checkpoint["state"]) != "active"
        ):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Reconciliation checkpoint identity conflicts")
        cursor = self._cursor(checkpoint["cursor_value_private"], manifest)
        if cursor["last_event_id"] is not None:
            last_run_id = "run_reconcile_" + _event_suffix(cursor["last_event_id"])
            last_run = connection.execute(
                "SELECT run_kind, state, input_manifest_hash FROM run_record WHERE run_id = ?",
                (last_run_id,),
            ).fetchone()
            if (
                last_run is None
                or str(last_run["run_kind"]) != RUN_KIND
                or str(last_run["state"]) != "succeeded"
                or str(last_run["input_manifest_hash"]) != cursor["last_input_sha256"]
            ):
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Reconciliation cursor lost its Run ledger")
        return checkpoint, cursor

    @staticmethod
    def _replayed_source_full_scan_ref(connection: Any, manifest: ReconciliationManifest) -> str | None:
        if manifest.outcome != "complete_success":
            return None
        assert manifest.source_checkpoint_id is not None
        assert manifest.source_scan_receipt_id is not None
        rule = SOURCE_RULES[manifest.source_adapter]
        assert rule.run_prefix is not None and rule.receipt_prefix is not None
        checkpoint = connection.execute(
            "SELECT adapter_name, adapter_version, account_ref_hash, relation_type, cursor_kind, "
            "completion_confidence, state, full_scan_id FROM checkpoint WHERE checkpoint_id = ?",
            (manifest.source_checkpoint_id,),
        ).fetchone()
        if (
            checkpoint is None
            or str(checkpoint["adapter_name"]) != manifest.source_adapter
            or str(checkpoint["adapter_version"]) != "1.0.0"
            or str(checkpoint["account_ref_hash"]) != manifest.account_ref_hash
            or str(checkpoint["relation_type"]) != manifest.relation_type.value
            or str(checkpoint["cursor_kind"]) != "authoritative_visible_end"
            or float(checkpoint["completion_confidence"]) != 1.0
            or str(checkpoint["state"]) != "complete"
            or checkpoint["full_scan_id"] is None
        ):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Replayed source checkpoint diverged")
        full_scan_id = str(checkpoint["full_scan_id"])
        if not full_scan_id.startswith(rule.run_prefix):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Replayed source full-scan identity diverged")
        suffix = full_scan_id.removeprefix(rule.run_prefix)
        if not suffix or manifest.source_scan_receipt_id != rule.receipt_prefix + suffix:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Replayed source receipt diverged")
        run = connection.execute(
            "SELECT run_kind, state FROM run_record WHERE run_id = ?",
            (full_scan_id,),
        ).fetchone()
        if run is None or str(run["run_kind"]) != rule.source_run_kind or str(run["state"]) != "succeeded":
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Replayed source Run diverged")
        return _sha256(full_scan_id)

    @staticmethod
    def _validate_source_full_scan(connection: Any, manifest: ReconciliationManifest) -> tuple[str, str]:
        rule = SOURCE_RULES[manifest.source_adapter]
        assert rule.authoritative_full_scan
        assert manifest.source_checkpoint_id is not None
        assert manifest.source_scan_receipt_id is not None
        checkpoint = connection.execute(
            "SELECT * FROM checkpoint WHERE checkpoint_id = ?",
            (manifest.source_checkpoint_id,),
        ).fetchone()
        if (
            checkpoint is None
            or str(checkpoint["adapter_name"]) != manifest.source_adapter
            or str(checkpoint["adapter_version"]) != "1.0.0"
            or str(checkpoint["account_ref_hash"]) != manifest.account_ref_hash
            or str(checkpoint["relation_type"]) != manifest.relation_type.value
            or str(checkpoint["cursor_kind"]) != "authoritative_visible_end"
            or str(checkpoint["state"]) != "complete"
            or float(checkpoint["completion_confidence"]) != 1.0
            or checkpoint["full_scan_id"] is None
        ):
            raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Source checkpoint is not authoritative")
        full_scan_id = str(checkpoint["full_scan_id"])
        assert rule.run_prefix is not None and rule.receipt_prefix is not None and rule.source_run_kind is not None
        if not full_scan_id.startswith(rule.run_prefix):
            raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Source full-scan identity is invalid")
        suffix = full_scan_id.removeprefix(rule.run_prefix)
        if not suffix or manifest.source_scan_receipt_id != rule.receipt_prefix + suffix:
            raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Source scan receipt does not match the full scan")
        run = connection.execute(
            "SELECT run_kind, state, started_at, finished_at FROM run_record WHERE run_id = ?",
            (full_scan_id,),
        ).fetchone()
        if (
            run is None
            or str(run["run_kind"]) != rule.source_run_kind
            or str(run["state"]) != "succeeded"
            or run["finished_at"] is None
        ):
            raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Source full-scan Run is incomplete")
        source_checkpoint_time = _stored_utc(
            checkpoint["updated_at"],
            ErrorCode.PROVENANCE_INCOMPLETE,
            "Source checkpoint time is invalid",
        )
        source_run_finished_at = _stored_utc(
            run["finished_at"],
            ErrorCode.PROVENANCE_INCOMPLETE,
            "Source Run time is invalid",
        )
        source_run_started_at = _stored_utc(
            run["started_at"],
            ErrorCode.PROVENANCE_INCOMPLETE,
            "Source Run time is invalid",
        )
        if (
            source_run_started_at > source_run_finished_at
            or source_run_finished_at > source_checkpoint_time
            or source_checkpoint_time > _utc(manifest.observed_at)
        ):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Source evidence time is inconsistent")
        source_checkpoint_at = _timestamp(source_checkpoint_time)

        observations = connection.execute(
            "SELECT content_key, adapter_name, adapter_version, source_method FROM source_observation "
            "WHERE run_id = ? ORDER BY observation_id",
            (full_scan_id,),
        ).fetchall()
        observation_keys = {str(row["content_key"]) for row in observations}
        assert rule.source_observation_method is not None
        if (
            len(observation_keys) != int(checkpoint["observed_count"])
            or len(observation_keys) != manifest.source_observed_content_count
            or any(str(row["adapter_name"]) != manifest.source_adapter for row in observations)
            or any(str(row["adapter_version"]) != "1.0.0" for row in observations)
            or any(str(row["source_method"]) != rule.source_observation_method for row in observations)
        ):
            raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Source observation count is incomplete")

        source_relations = connection.execute(
            """
            SELECT ur.relation_key, ur.content_key, ur.status, ur.confirmed_by, c.platform
            FROM user_relation AS ur
            JOIN content AS c ON c.content_key = ur.content_key
            WHERE ur.account_ref_hash = ? AND ur.relation_type = ? AND ur.scan_receipt_id = ?
            ORDER BY ur.relation_key
            """,
            (
                manifest.account_ref_hash,
                manifest.relation_type.value,
                manifest.source_scan_receipt_id,
            ),
        ).fetchall()
        source_keys = {str(row["relation_key"]) for row in source_relations}
        if source_keys != set(manifest.observed_relation_keys):
            raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Source relation manifest is not exact")
        if (
            any(str(row["status"]) != RelationStatus.ACTIVE.value for row in source_relations)
            or any(str(row["confirmed_by"]) != ConfirmationSource.SCAN.value for row in source_relations)
            or any(str(row["platform"]) != manifest.platform.value for row in source_relations)
            or {str(row["content_key"]) for row in source_relations} != observation_keys
        ):
            raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Source relation observations are incomplete")
        return full_scan_id, source_checkpoint_at

    def _update_relation(
        self,
        connection: Any,
        row: Any,
        *,
        status: RelationStatus,
        receipt_id: str,
        platform: Platform,
        timestamp: str,
    ) -> WriteDisposition:
        relation = self._relation_from_row(row)
        updated = relation.model_copy(update={"status": status, "scan_receipt_id": receipt_id})
        return self.store._upsert_relation(connection, updated, platform.value, timestamp)

    @staticmethod
    def _validate_pending_scope(
        rows: Sequence[Any],
        cursor: Mapping[str, Any],
        *,
        currently_observed: Sequence[str] = (),
    ) -> None:
        unknown_keys = {str(row["relation_key"]) for row in rows if str(row["status"]) == RelationStatus.UNKNOWN.value}
        active_observed_keys = {
            str(row["relation_key"])
            for row in rows
            if str(row["status"]) == RelationStatus.ACTIVE.value and str(row["relation_key"]) in currently_observed
        }
        if not set(cursor["pending_missing_relation_keys"]) <= unknown_keys | active_observed_keys:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Reconciliation pending set escaped unknown scope")

    @staticmethod
    def _counts_from_rows(rows: Sequence[Any]) -> dict[str, int]:
        return {
            "candidate": sum(str(row["status"]) == RelationStatus.TOMBSTONE_CANDIDATE.value for row in rows),
            "removed": sum(str(row["status"]) == RelationStatus.REMOVED.value for row in rows),
            "scope": len(rows),
            "unknown": sum(str(row["status"]) == RelationStatus.UNKNOWN.value for row in rows),
        }

    @staticmethod
    def _current_counts(connection: Any, manifest: ReconciliationManifest) -> dict[str, int]:
        return RelationReconciler._counts_from_rows(RelationReconciler._scope_rows(connection, manifest))

    def _replay_receipt(
        self,
        connection: Any,
        manifest: ReconciliationManifest,
        cursor: Mapping[str, Any],
    ) -> ReconciliationReceipt:
        rows = self._scope_rows(connection, manifest)
        self._validate_pending_scope(rows, cursor)
        counts = self._counts_from_rows(rows)
        return ReconciliationReceipt(
            disposition="replayed",
            outcome=manifest.outcome,
            scope_ref_sha256=manifest.scope_hash(),
            source_full_scan_ref_sha256=self._replayed_source_full_scan_ref(connection, manifest),
            source_scan_receipt_ref_sha256=(
                _sha256(manifest.source_scan_receipt_id) if manifest.source_scan_receipt_id is not None else None
            ),
            full_scan_verified=manifest.outcome == "complete_success",
            observed_relation_count=len(manifest.observed_relation_keys),
            source_observed_content_count=manifest.source_observed_content_count,
            scope_relation_count=counts["scope"],
            missing_relation_count=0,
            unknown_transition_count=0,
            tombstone_candidate_transition_count=0,
            tombstone_candidate_total=counts["candidate"],
            reactivated_count=0,
            pending_missing_count=len(cursor["pending_missing_relation_keys"]),
            removed_preserved_count=counts["removed"],
        )

    def process(self, manifest: ReconciliationManifest) -> ReconciliationReceipt:
        identity = self._identity(manifest)
        timestamp = _timestamp(manifest.observed_at)
        input_hash = manifest.input_hash()
        with self.store._transaction() as connection:
            existing_run = connection.execute(
                "SELECT run_kind, state, input_manifest_hash FROM run_record WHERE run_id = ?",
                (identity["run_id"],),
            ).fetchone()
            if existing_run is not None:
                if (
                    str(existing_run["run_kind"]) != RUN_KIND
                    or str(existing_run["state"]) != "succeeded"
                    or str(existing_run["input_manifest_hash"]) != input_hash
                ):
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Reconciliation event identity conflicts")
                checkpoint, cursor = self._ensure_scope_checkpoint(
                    connection,
                    manifest,
                    identity,
                    timestamp,
                    create_if_missing=False,
                )
                del checkpoint
                if cursor["last_event_id"] != manifest.event_id and (
                    cursor["last_observed_at"] is None or cursor["last_observed_at"] <= timestamp
                ):
                    raise X2NRuntimeError(
                        ErrorCode.DATA_INTEGRITY_FAILED,
                        "Successful reconciliation Run is absent from the durable cursor",
                    )
                return self._replay_receipt(connection, manifest, cursor)

            checkpoint, cursor = self._ensure_scope_checkpoint(connection, manifest, identity, timestamp)
            previous_time = cursor["last_observed_at"]
            if previous_time is not None and timestamp <= previous_time:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Reconciliation event time did not advance")
            connection.execute(
                """
                INSERT INTO run_record(
                    run_id, run_kind, state, input_manifest_hash, started_at, finished_at, created_at
                ) VALUES (?, ?, 'running', ?, ?, NULL, ?)
                """,
                (identity["run_id"], RUN_KIND, input_hash, timestamp, timestamp),
            )

            scope_rows = self._scope_rows(connection, manifest)
            self._validate_pending_scope(
                scope_rows,
                cursor,
                currently_observed=manifest.observed_relation_keys,
            )
            previous_pending = set(cursor["pending_missing_relation_keys"])
            source_full_scan_id: str | None = None
            source_checkpoint_at: str | None = None
            missing_count = unknown_changes = candidate_changes = reactivated = 0

            self._fault("before_reconciliation")
            if manifest.outcome in NON_AUTHORITATIVE_OUTCOMES:
                pending_after: list[str] = []
                cursor_kind = "non_authoritative_no_relation_change"
                confidence = 0.0
                cursor["total_non_authoritative_events"] += 1
            else:
                source_full_scan_id, source_checkpoint_at = self._validate_source_full_scan(connection, manifest)
                source_full_scan_ref = _sha256(source_full_scan_id)
                if (
                    cursor["last_source_full_scan_ref_sha256"] == source_full_scan_ref
                    or cursor["last_source_checkpoint_at"] is not None
                    and source_checkpoint_at <= cursor["last_source_checkpoint_at"]
                ):
                    raise X2NRuntimeError(
                        ErrorCode.DATA_INTEGRITY_FAILED,
                        "Reconciliation requires a newer distinct authoritative full scan",
                    )
                observed = set(manifest.observed_relation_keys)
                scope_by_key = {str(row["relation_key"]): row for row in scope_rows}
                if not observed <= set(scope_by_key):
                    raise X2NRuntimeError(ErrorCode.PROVENANCE_INCOMPLETE, "Observed relation escaped its scope")
                mutable_rows = {
                    key: row for key, row in scope_by_key.items() if str(row["status"]) != RelationStatus.REMOVED.value
                }
                missing = sorted(set(mutable_rows) - observed)
                missing_count = len(missing)
                pending_after = []
                for index, key in enumerate(sorted(observed)):
                    row = mutable_rows[key]
                    if str(row["status"]) != RelationStatus.ACTIVE.value:
                        if (
                            self._update_relation(
                                connection,
                                row,
                                status=RelationStatus.ACTIVE,
                                receipt_id=manifest.source_scan_receipt_id or identity["receipt_id"],
                                platform=manifest.platform,
                                timestamp=timestamp,
                            )
                            is not WriteDisposition.UNCHANGED
                        ):
                            reactivated += 1
                    self._fault(f"after_observed_{index}")
                for index, key in enumerate(missing):
                    row = mutable_rows[key]
                    current = RelationStatus(str(row["status"]))
                    target = current
                    if current is RelationStatus.ACTIVE:
                        target = RelationStatus.UNKNOWN
                    elif current is RelationStatus.UNKNOWN and key in previous_pending:
                        target = RelationStatus.TOMBSTONE_CANDIDATE
                    if target is RelationStatus.UNKNOWN:
                        pending_after.append(key)
                    if target is not current:
                        disposition = self._update_relation(
                            connection,
                            row,
                            status=target,
                            receipt_id=identity["receipt_id"],
                            platform=manifest.platform,
                            timestamp=timestamp,
                        )
                        if disposition is not WriteDisposition.UNCHANGED:
                            unknown_changes += int(target is RelationStatus.UNKNOWN)
                            candidate_changes += int(target is RelationStatus.TOMBSTONE_CANDIDATE)
                    self._fault(f"after_missing_{index}")
                cursor_kind = "authoritative_full_scan_reconciled"
                confidence = 1.0
                cursor["total_complete_scans"] += 1

            cursor.update(
                {
                    "last_event_id": manifest.event_id,
                    "last_input_sha256": input_hash,
                    "last_observed_at": timestamp,
                    "last_outcome": manifest.outcome,
                    "pending_missing_relation_keys": sorted(pending_after),
                }
            )
            if source_full_scan_id is not None:
                cursor["last_source_checkpoint_at"] = source_checkpoint_at
                cursor["last_source_full_scan_ref_sha256"] = _sha256(source_full_scan_id)
            self._fault("before_checkpoint")
            updated = connection.execute(
                """
                UPDATE checkpoint SET
                    cursor_kind = ?, cursor_value_private = ?, full_scan_id = ?, observed_count = ?,
                    completion_confidence = ?, updated_at = ?
                WHERE checkpoint_id = ? AND state = 'active'
                """,
                (
                    cursor_kind,
                    _canonical_json(cursor),
                    source_full_scan_id,
                    len(manifest.observed_relation_keys),
                    confidence,
                    timestamp,
                    identity["checkpoint_id"],
                ),
            )
            if updated.rowcount != 1:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Reconciliation checkpoint update conflicted")
            self._fault("after_checkpoint")
            finished = connection.execute(
                "UPDATE run_record SET state = 'succeeded', finished_at = ? WHERE run_id = ? AND state = 'running'",
                (timestamp, identity["run_id"]),
            )
            if finished.rowcount != 1:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Reconciliation Run completion conflicted")
            self._fault("before_commit")

            counts = self._current_counts(connection, manifest)
            return ReconciliationReceipt(
                disposition="applied",
                outcome=manifest.outcome,
                scope_ref_sha256=identity["scope_hash"],
                source_full_scan_ref_sha256=(_sha256(source_full_scan_id) if source_full_scan_id is not None else None),
                source_scan_receipt_ref_sha256=(
                    _sha256(manifest.source_scan_receipt_id) if manifest.source_scan_receipt_id is not None else None
                ),
                full_scan_verified=source_full_scan_id is not None,
                observed_relation_count=len(manifest.observed_relation_keys),
                source_observed_content_count=manifest.source_observed_content_count,
                scope_relation_count=counts["scope"],
                missing_relation_count=missing_count,
                unknown_transition_count=unknown_changes,
                tombstone_candidate_transition_count=candidate_changes,
                tombstone_candidate_total=counts["candidate"],
                reactivated_count=reactivated,
                pending_missing_count=len(pending_after),
                removed_preserved_count=counts["removed"],
            )
