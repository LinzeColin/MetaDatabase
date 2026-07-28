"""Canonical SQLite adapter for sanitized, pinned Douyin sidecar batches."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Callable
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
from .canonical_store import CanonicalStore
from .douyin_upstream import DouyinBatch, DouyinBatchRequest, DouyinItem, Mode, PinnedDouyinClient
from .runtime import X2NRuntimeError


TASK_ID = "TSK.x2n.adapters.004"
ADAPTER_NAME = "douyin_upstream"
ADAPTER_VERSION = "1.0.0"
RESUME_COMPATIBILITY_VERSION = "douyin-upstream-1.0.0"
RUN_KIND = "douyin_owner_bounded_scan_v1"
CANARY_ITEM_LIMIT = 20
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ScopeMode = Literal["canary_20", "owner_bounded"]
FaultInjector = Callable[[str], None]


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _scan_uuid(value: str) -> uuid.UUID:
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, TypeError, ValueError):
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Douyin scan identity is invalid") from None
    if str(parsed) != value:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Douyin scan identity is not canonical")
    return parsed


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Douyin observation time requires a timezone")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _timestamp(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _identity(scan_id: str) -> dict[str, str]:
    suffix = _scan_uuid(scan_id).hex
    return {
        "checkpoint_id": f"checkpoint_dy_{suffix}",
        "run_id": f"run_dy_{suffix}",
        "scan_receipt_id": f"receipt_dy_{suffix}",
    }


def _canonical_page_url(content_id: str) -> str:
    return f"https://www.douyin.com/video/{content_id}"


def _relation_type(mode: Mode) -> RelationType:
    return RelationType.FAVORITED if mode == "favorites" else RelationType.LIKED


def _require_graph_state(run_state: Any, checkpoint_state: Any) -> None:
    if (run_state, checkpoint_state) not in {("running", "active"), ("succeeded", "complete")}:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Douyin scan graph state is inconsistent")


@dataclass(frozen=True)
class DouyinReceipt:
    scan_ref_sha256: str
    disposition: Literal["applied", "replayed"]
    checkpoint_state: Literal["active", "complete"]
    cursor_kind: str
    mode: Mode
    next_sequence: int
    observed_unique_items: int
    relation_count: int
    observation_count: int
    error_evidence_count: int

    def safe_dict(self) -> dict[str, Any]:
        return {
            "adapter": {"name": ADAPTER_NAME, "version": ADAPTER_VERSION},
            "automatic_pagination": 0,
            "checkpoint": {
                "cursor_kind": self.cursor_kind,
                "next_sequence": self.next_sequence,
                "state": self.checkpoint_state,
            },
            "content_auto_deletes": 0,
            "disposition": self.disposition,
            "error_evidence_count": self.error_evidence_count,
            "full_scan_completed": False,
            "mode": self.mode,
            "observations": self.observation_count,
            "observed_unique_items": self.observed_unique_items,
            "physical_deletes": 0,
            "private_path_emitted": False,
            "relations": self.relation_count,
            "removed_relations": 0,
            "scan_ref_sha256": self.scan_ref_sha256,
            "schema_version": "1.0",
            "task_id": TASK_ID,
        }


def build_douyin_canary_plan(mode: Mode, max_items: int = CANARY_ITEM_LIMIT) -> dict[str, Any]:
    if mode not in {"favorites", "likes"} or max_items != CANARY_ITEM_LIMIT:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin Canary is fixed to one 20-item mode")
    return {
        "acceptance_id": "ACC.x2n.dy.001" if mode == "favorites" else "ACC.x2n.dy.002",
        "adapter": ADAPTER_NAME,
        "automatic_pagination": False,
        "execution": "NOT_RUN",
        "feature_flag": f"douyin_{mode}",
        "max_items": CANARY_ITEM_LIMIT,
        "mode": mode,
        "owner_authorization_required": True,
        "preconditions": [
            "dedicated_profile_healthy",
            "owner_explicit_action",
            "private_sidecar_exact_build_attested",
            "private_gold_manifest_ready",
            "policy_recheck_current",
            "stop_control_visible",
        ],
        "production_enabled": False,
        "real_account_execution": "NOT_RUN",
        "rollback": f"disable_douyin_{mode}_keep_current_page",
        "task_id": TASK_ID,
        "upstream_runtime": "OWNER_PRIVATE_SIDECAR_NOT_INSTALLED",
    }


class DouyinAdapter:
    """Atomic relation/checkpoint writer for one already-sanitized batch."""

    def __init__(self, store: CanonicalStore, *, fault_injector: FaultInjector | None = None) -> None:
        self.store = store
        self._fault_injector = fault_injector

    def _fault(self, label: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector(label)

    @staticmethod
    def _initial_cursor(mode: Mode, scope_mode: ScopeMode) -> dict[str, Any]:
        return {
            "error_evidence_count": 0,
            "last_batch_hash": None,
            "last_error_codes": [],
            "last_outcome": "not_started",
            "last_sequence": None,
            "mode": mode,
            "next_sequence": 0,
            "scope_mode": scope_mode,
        }

    @staticmethod
    def _cursor(raw: str | None) -> dict[str, Any]:
        try:
            value = json.loads(raw or "")
        except json.JSONDecodeError:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Douyin checkpoint cursor is invalid") from None
        expected = {
            "error_evidence_count",
            "last_batch_hash",
            "last_error_codes",
            "last_outcome",
            "last_sequence",
            "mode",
            "next_sequence",
            "scope_mode",
        }
        if not isinstance(value, dict) or set(value) != expected:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Douyin checkpoint cursor is invalid")
        valid_next_sequence = (
            isinstance(value.get("next_sequence"), int)
            and not isinstance(value.get("next_sequence"), bool)
            and value["next_sequence"] >= 0
        )
        valid_error_count = (
            isinstance(value.get("error_evidence_count"), int)
            and not isinstance(value.get("error_evidence_count"), bool)
            and value["error_evidence_count"] >= 0
        )
        last_sequence = value.get("last_sequence")
        valid_last_sequence = last_sequence is None or (
            isinstance(last_sequence, int) and not isinstance(last_sequence, bool) and last_sequence >= 0
        )
        valid_last_hash = value.get("last_batch_hash") is None or (
            isinstance(value.get("last_batch_hash"), str) and SHA256.fullmatch(value["last_batch_hash"]) is not None
        )
        outcomes = {
            "not_started",
            "ready",
            "partial",
            "auth_required",
            "empty_unverified",
            "platform_changed",
            "rate_limited",
            "upstream_error",
        }
        initial = (
            last_sequence is None
            and value.get("last_batch_hash") is None
            and value.get("last_outcome") == "not_started"
            and value.get("next_sequence") == 0
            and value.get("error_evidence_count") == 0
            and value.get("last_error_codes") == []
        )
        progressed = (
            valid_next_sequence
            and valid_error_count
            and isinstance(value.get("last_error_codes"), list)
            and valid_last_sequence
            and last_sequence is not None
            and valid_last_hash
            and value.get("last_batch_hash") is not None
            and value.get("last_outcome") in outcomes - {"not_started"}
            and value.get("next_sequence") == last_sequence + (1 if value.get("last_outcome") == "ready" else 0)
            and value.get("error_evidence_count") >= len(value.get("last_error_codes", []))
        )
        if (
            value["mode"] not in {"favorites", "likes"}
            or value["scope_mode"] not in {"canary_20", "owner_bounded"}
            or not valid_next_sequence
            or not valid_error_count
            or not isinstance(value["last_error_codes"], list)
            or any(code not in {item.value for item in ErrorCode} for code in value["last_error_codes"])
            or not valid_last_sequence
            or not valid_last_hash
            or value["last_outcome"] not in outcomes
            or not (initial or progressed)
        ):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Douyin checkpoint cursor is invalid")
        return value

    def begin_scan(
        self,
        scan_id: str,
        *,
        account_ref_hash: str,
        mode: Mode,
        scope_mode: ScopeMode,
        started_at: datetime,
    ) -> DouyinReceipt:
        identity = _identity(scan_id)
        if SHA256.fullmatch(account_ref_hash) is None:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Douyin account reference is invalid")
        if mode not in {"favorites", "likes"} or scope_mode not in {"canary_20", "owner_bounded"}:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Douyin scan scope is invalid")
        timestamp = _timestamp(started_at)
        input_hash = _sha256({"account_ref_hash": account_ref_hash, "mode": mode, "scope_mode": scope_mode})
        relation_type = _relation_type(mode).value
        with self.store._transaction() as connection:
            run = connection.execute(
                "SELECT run_kind, state, input_manifest_hash FROM run_record WHERE run_id = ?",
                (identity["run_id"],),
            ).fetchone()
            checkpoint = connection.execute(
                "SELECT * FROM checkpoint WHERE checkpoint_id = ?", (identity["checkpoint_id"],)
            ).fetchone()
            if (run is None) != (checkpoint is None):
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Douyin scan graph is incomplete")
            if run is None:
                connection.execute(
                    "INSERT OR IGNORE INTO account_ref(account_ref_hash, platform, created_at) VALUES (?, ?, ?)",
                    (account_ref_hash, Platform.DOUYIN.value, timestamp),
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
                    ) VALUES (?, ?, ?, ?, ?, 'owner_bounded_batch', ?, NULL, NULL, 0, 0.0, ?, 'active', ?, ?)
                    """,
                    (
                        identity["checkpoint_id"],
                        ADAPTER_NAME,
                        ADAPTER_VERSION,
                        account_ref_hash,
                        relation_type,
                        _canonical_json(self._initial_cursor(mode, scope_mode)),
                        RESUME_COMPATIBILITY_VERSION,
                        timestamp,
                        timestamp,
                    ),
                )
                checkpoint = connection.execute(
                    "SELECT * FROM checkpoint WHERE checkpoint_id = ?", (identity["checkpoint_id"],)
                ).fetchone()
            else:
                cursor = self._cursor(checkpoint["cursor_value_private"])
                _require_graph_state(run["state"], checkpoint["state"])
                if (
                    run["run_kind"] != RUN_KIND
                    or run["input_manifest_hash"] != input_hash
                    or checkpoint["adapter_name"] != ADAPTER_NAME
                    or checkpoint["adapter_version"] != ADAPTER_VERSION
                    or checkpoint["account_ref_hash"] != account_ref_hash
                    or checkpoint["relation_type"] != relation_type
                    or checkpoint["resume_compatibility_version"] != RESUME_COMPATIBILITY_VERSION
                    or cursor["mode"] != mode
                    or cursor["scope_mode"] != scope_mode
                ):
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Douyin scan identity conflicts")
            assert checkpoint is not None
            return self._receipt(connection, scan_id, checkpoint, disposition="replayed" if run else "applied")

    @staticmethod
    def _content(connection: Any, item: DouyinItem, observed_at: datetime) -> CanonicalContent:
        content_key = build_content_key(Platform.DOUYIN, item.content_id)
        row = connection.execute("SELECT payload_json FROM content WHERE content_key = ?", (content_key,)).fetchone()
        first = observed_at
        version = 1
        if row is not None:
            stored = CanonicalContent.model_validate_json(row["payload_json"])
            if observed_at < stored.last_observed_at:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Douyin content time moved backwards")
            first = stored.first_observed_at
            version = stored.record_version if observed_at == stored.last_observed_at else stored.record_version + 1
        return CanonicalContent(
            schema_version="1.0",
            content_key=content_key,
            platform=Platform.DOUYIN,
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
        item: DouyinItem,
        *,
        account_ref_hash: str,
        mode: Mode,
        scan_receipt_id: str,
        observed_at: datetime,
    ) -> UserRelation:
        content_key = build_content_key(Platform.DOUYIN, item.content_id)
        relation_type = _relation_type(mode)
        collection_key = item.collection.key if item.collection is not None else None
        relation_key = build_relation_key(account_ref_hash, content_key, relation_type, collection_key)
        row = connection.execute(
            "SELECT payload_json FROM user_relation WHERE relation_key = ?", (relation_key,)
        ).fetchone()
        first = observed_at
        if row is not None:
            stored = UserRelation.model_validate_json(row["payload_json"])
            if observed_at < stored.last_seen_at:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Douyin relation time moved backwards")
            first = stored.first_seen_at
        return UserRelation(
            schema_version="1.0",
            relation_key=relation_key,
            account_ref_hash=account_ref_hash,
            content_key=content_key,
            relation_type=relation_type,
            source_collection_id=collection_key,
            source_collection_name_private=item.collection.name_private if item.collection is not None else None,
            first_seen_at=first,
            last_seen_at=observed_at,
            status=RelationStatus.ACTIVE,
            confirmed_by=ConfirmationSource.SCAN,
            scan_receipt_id=scan_receipt_id,
        )

    @staticmethod
    def _observation(
        item: DouyinItem,
        *,
        mode: Mode,
        scan_id: str,
        run_id: str,
        observed_at: datetime,
        warning_codes: tuple[ErrorCode, ...],
    ) -> SourceObservation:
        parsed = _scan_uuid(scan_id)
        facts_hash = _sha256(item.facts())
        observation_id = f"obs_{uuid.uuid5(parsed, f'douyin:{mode}:{facts_hash}:{_timestamp(observed_at)}').hex}"
        fields = (
            CanonicalField.PLATFORM_CONTENT_ID,
            CanonicalField.CANONICAL_SOURCE_URL,
            CanonicalField.CONTENT_TYPE,
            CanonicalField.TITLE,
        )
        return SourceObservation(
            schema_version="1.0",
            observation_id=observation_id,
            content_key=build_content_key(Platform.DOUYIN, item.content_id),
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
                    status=FieldStatus.UNKNOWN if item.content_type == "unknown" else FieldStatus.PRESENT,
                    confidence=0.5 if item.content_type == "unknown" else 1.0,
                ),
                FieldProvenance(
                    field=CanonicalField.TITLE,
                    source=FieldSource.ADAPTER,
                    status=FieldStatus.UNKNOWN if item.title is None else FieldStatus.PRESENT,
                    confidence=0.0 if item.title is None else 1.0,
                ),
            ),
            completeness=sum((1, 1, int(item.content_type != "unknown"), int(item.title is not None))) / 4,
            warning_codes=warning_codes,
            ephemeral_media_ref_ids=(),
            run_id=run_id,
        )

    def commit_batch(self, scan_id: str, batch: DouyinBatch, *, observed_at: datetime) -> DouyinReceipt:
        identity = _identity(scan_id)
        normalized_time = _utc(observed_at)
        timestamp = _timestamp(normalized_time)
        batch_hash = _sha256(
            {
                "completion_signal": batch.completion_signal,
                "error_codes": [item.value for item in batch.error_codes],
                "items": [item.facts() for item in batch.items],
                "mode": batch.mode,
                "observed_at": timestamp,
                "sequence": batch.sequence,
                "status": batch.status,
            }
        )
        with self.store._transaction() as connection:
            checkpoint = connection.execute(
                "SELECT * FROM checkpoint WHERE checkpoint_id = ?", (identity["checkpoint_id"],)
            ).fetchone()
            run = connection.execute("SELECT state FROM run_record WHERE run_id = ?", (identity["run_id"],)).fetchone()
            if checkpoint is None or run is None:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Douyin scan is not initialized")
            _require_graph_state(run["state"], checkpoint["state"])
            if timestamp < str(checkpoint["updated_at"]):
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Douyin checkpoint time moved backwards")
            cursor = self._cursor(checkpoint["cursor_value_private"])
            if cursor["mode"] != batch.mode:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Douyin batch mode conflicts")
            if cursor["last_sequence"] == batch.sequence and cursor["last_batch_hash"] == batch_hash:
                return self._receipt(connection, scan_id, checkpoint, disposition="replayed")
            if batch.sequence < cursor["next_sequence"] or checkpoint["state"] == "complete":
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Douyin replay does not match checkpoint")
            if batch.sequence != cursor["next_sequence"]:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Douyin batch is not the checkpoint successor")

            account_ref_hash = str(checkpoint["account_ref_hash"])
            for index, item in enumerate(batch.items):
                content = self._content(connection, item, normalized_time)
                self.store._upsert_content(connection, content, timestamp)
                relation = self._relation(
                    connection,
                    item,
                    account_ref_hash=account_ref_hash,
                    mode=batch.mode,
                    scan_receipt_id=identity["scan_receipt_id"],
                    observed_at=normalized_time,
                )
                self.store._upsert_relation(connection, relation, Platform.DOUYIN.value, timestamp)
                observation = self._observation(
                    item,
                    mode=batch.mode,
                    scan_id=scan_id,
                    run_id=identity["run_id"],
                    observed_at=normalized_time,
                    warning_codes=batch.error_codes,
                )
                self.store._append_observation(connection, observation, timestamp)
                self._fault(f"after_item_{index}")

            observed_count = int(
                connection.execute(
                    "SELECT COUNT(DISTINCT content_key) FROM source_observation WHERE run_id = ?",
                    (identity["run_id"],),
                ).fetchone()[0]
            )
            advances = batch.status == "ready"
            next_sequence = batch.sequence + 1 if advances else batch.sequence
            cursor.update(
                {
                    "error_evidence_count": cursor["error_evidence_count"] + len(batch.error_codes),
                    "last_batch_hash": batch_hash,
                    "last_error_codes": [item.value for item in batch.error_codes],
                    "last_outcome": batch.status,
                    "last_sequence": batch.sequence,
                    "next_sequence": next_sequence,
                }
            )
            bounded_complete = (
                batch.status == "ready"
                and batch.completion_signal == "bounded_limit_reached"
                and observed_count == CANARY_ITEM_LIMIT
            )
            if batch.completion_signal == "bounded_limit_reached" and not bounded_complete:
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Douyin bounded completion is invalid")
            state = "complete" if bounded_complete else "active"
            cursor_kind = "bounded_scope_complete" if bounded_complete else "owner_bounded_batch"
            confidence = 1.0 if bounded_complete else 0.0
            last_stable = batch.items[-1].content_id if batch.items else checkpoint["last_stable_content_id"]
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
                    confidence,
                    state,
                    timestamp,
                    identity["checkpoint_id"],
                ),
            )
            if updated.rowcount != 1:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Douyin checkpoint transition conflicted")
            self._fault("after_checkpoint")
            if state == "complete":
                run_update = connection.execute(
                    "UPDATE run_record SET state = 'succeeded', finished_at = ? WHERE run_id = ? AND state = 'running'",
                    (timestamp, identity["run_id"]),
                )
                if run_update.rowcount != 1:
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Douyin Run transition conflicted")
            self._fault("before_commit")
            refreshed = connection.execute(
                "SELECT * FROM checkpoint WHERE checkpoint_id = ?", (identity["checkpoint_id"],)
            ).fetchone()
            if refreshed is None:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Douyin checkpoint disappeared")
            return self._receipt(connection, scan_id, refreshed, disposition="applied")

    def checkpoint(self, scan_id: str) -> DouyinReceipt:
        identity = _identity(scan_id)
        with self.store._file_lock(exclusive=False):
            connection = self.store._open(writable=False)
            try:
                checkpoint = connection.execute(
                    "SELECT * FROM checkpoint WHERE checkpoint_id = ?", (identity["checkpoint_id"],)
                ).fetchone()
                run = connection.execute(
                    "SELECT state FROM run_record WHERE run_id = ?", (identity["run_id"],)
                ).fetchone()
                if checkpoint is None or run is None:
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Douyin checkpoint is unavailable")
                _require_graph_state(run["state"], checkpoint["state"])
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
    ) -> DouyinReceipt:
        identity = _identity(scan_id)
        cursor = self._cursor(checkpoint["cursor_value_private"])
        relation_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM user_relation WHERE scan_receipt_id = ?", (identity["scan_receipt_id"],)
            ).fetchone()[0]
        )
        observation_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM source_observation WHERE run_id = ?", (identity["run_id"],)
            ).fetchone()[0]
        )
        return DouyinReceipt(
            scan_ref_sha256=hashlib.sha256(scan_id.encode("ascii")).hexdigest(),
            disposition=disposition,
            checkpoint_state=checkpoint["state"],
            cursor_kind=checkpoint["cursor_kind"],
            mode=cursor["mode"],
            next_sequence=cursor["next_sequence"],
            observed_unique_items=int(checkpoint["observed_count"]),
            relation_count=relation_count,
            observation_count=observation_count,
            error_evidence_count=cursor["error_evidence_count"],
        )


class DouyinBatchCoordinator:
    """Perform exactly one guarded transport call and one atomic commit."""

    def __init__(
        self,
        adapter: DouyinAdapter,
        client: PinnedDouyinClient,
        guard: AdapterExecutionGate,
    ) -> None:
        self.adapter = adapter
        self.client = client
        self.guard = guard

    def apply_owner_action(
        self,
        scan_id: str,
        request: DouyinBatchRequest,
        *,
        observed_at: datetime,
        monotonic_batch_time: float,
        monotonic_observation_time: float,
    ) -> DouyinReceipt:
        with self.guard.acquire(Platform.DOUYIN.value, now=monotonic_batch_time) as lease:
            lease.permit_item_observation(now=monotonic_observation_time)
            _health, batch = self.client.fetch_owner_batch(request)
            return self.adapter.commit_batch(scan_id, batch, observed_at=observed_at)
