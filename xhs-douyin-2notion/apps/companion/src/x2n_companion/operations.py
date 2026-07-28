"""Fail-closed operational diagnostics and restart recovery for Task004.

This module is deliberately an observer of the Canonical Store, never a second
source of truth.  Its persisted journal has a narrow schema: opaque run IDs,
stable error codes, stage state, and no free-form diagnostic text.  Recovery
uses the Canonical Store and deterministic sinks as the only authorities.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from x2n_contracts import ErrorCode

from .canonical_store import CanonicalStore, RecoveryPlan
from .markdown_sink import MarkdownRebuild, MarkdownSink
from .notion_sink import NotionSinkWorker
from .orchestrator import CurrentPageOrchestrator
from .profile_session import (
    DoctorProbe,
    DoctorReport,
    SessionHealth,
    SessionHealthStore,
    build_doctor_report,
    chrome_available,
    ffmpeg_available,
    native_host_registered,
    safe_reference_configured,
)
from .runtime import PROFILE_PLATFORMS, RuntimePaths, X2NRuntimeError, _atomic_private_json
from .sink_projection import build_sink_projection


TASK_ID = "TSK.x2n.uxops.004"
DIAGNOSTIC_SCHEMA_VERSION = "1.0"
RECOVERY_CONFIRMATION = "APPLY_LOCAL_OPERATIONS_RECOVERY"
JOURNAL_FILENAME = "operations-v1.json"
MAX_JOURNAL_EVENTS = 128
RECOVERY_STAGES = (
    "source",
    "media",
    "asr",
    "ocr",
    "vision",
    "fusion",
    "classification",
    "db_commit",
    "markdown",
    "notion",
)
EVENT_STATES = frozenset({"started", "succeeded", "failed", "skipped"})
DIAGNOSTIC_COMPONENTS = frozenset(
    {
        "canonical_store",
        "markdown_sink",
        "notion_sink",
        "pipeline",
        "startup_recovery",
    }
)
RUN_STATES = frozenset({"pending", "running", "succeeded", "failed", "cancelled", "recovery"})
OUTBOX_STATES = frozenset({"pending", "leased", "delivered", "dead_letter"})
CANONICAL_IDENTITY_TABLES = (
    "content",
    "user_relation",
    "source_observation",
    "classification",
)
DIAGNOSTIC_COUNT_TABLES = (
    *CANONICAL_IDENTITY_TABLES,
    "artifact",
    "outbox_event",
    "media_lease",
    "recovery_event",
    "run_record",
    "sink_receipt",
)
_EVENT_ID = re.compile(r"^evt_[0-9a-f]{32}$")
_RUN_ID = re.compile(r"^run_diag_[0-9a-f]{32}$")
_RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_FORBIDDEN_VALUE_PATTERNS = (
    re.compile(r"(?i)https?://"),
    re.compile(r"(?i)(?:bearer|cookie|set-cookie|authorization)"),
    re.compile(r"(?i)(?:github" + r"_pat_|gh[pousr]_[a-z0-9_]{8,})"),
    re.compile(r"(?i)(?:[?&](?:access[_-]?token|token|key|signature)=)"),
    re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+/"),
)
_FORBIDDEN_FIELD_NAMES = frozenset(
    {
        "authorization",
        "body",
        "canonical_source_url",
        "cookie",
        "credential",
        "description",
        "local_username",
        "model_output",
        "original_text",
        "profile_path",
        "query",
        "raw_text",
        "secret",
        "title",
        "token",
        "url",
    }
)
_EVENT_FIELDS = frozenset({"attempt", "component", "error_code", "event_id", "occurred_at", "run_id", "stage", "state"})
_JOURNAL_FIELDS = frozenset({"events", "schema_version"})
_DOCTOR_FIELDS = frozenset(
    {
        "components",
        "health_contract",
        "noncore_missing_disables_canonical",
        "observed_at",
        "overall",
        "private_path_emitted",
        "schema_version",
        "secret_emitted",
        "task_id",
    }
)
_RECOVERY_PLAN_FIELDS = frozenset(
    {
        "expired_media_leases",
        "expired_outbox_leases",
        "foreign_key_check",
        "foreign_key_violations",
        "integrity_check",
        "pending_outbox",
        "quick_check",
        "running_jobs",
    }
)
_RECOVERY_PLAN_BUNDLE_FIELDS = frozenset({"recovery", "schema_version", "task_id"})
_DIAGNOSTIC_BUNDLE_FIELDS = frozenset(
    {
        "canonical_counts",
        "data_lifecycle",
        "doctor",
        "journal",
        "metrics",
        "recovery",
        "schema_version",
        "task_id",
    }
)
_RECOVERY_RECEIPT_FIELDS = frozenset(
    {
        "append_only_artifacts",
        "canonical_core_counts",
        "current_page_resumed",
        "markdown",
        "notion",
        "recovery_after",
        "recovery_before",
        "run_id",
        "schema_version",
    }
)
_ALLOWED_ROOT_FIELD_SETS = frozenset(
    {
        _EVENT_FIELDS,
        _JOURNAL_FIELDS,
        _DOCTOR_FIELDS,
        _RECOVERY_PLAN_FIELDS,
        _RECOVERY_PLAN_BUNDLE_FIELDS,
        _DIAGNOSTIC_BUNDLE_FIELDS,
        _RECOVERY_RECEIPT_FIELDS,
    }
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _opaque_run_id(value: str) -> str:
    """Keep a stable correlation key without exporting an internal run identity."""

    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
    return f"run_diag_{digest}"


def _new_run_id() -> str:
    return f"run_diag_{uuid.uuid4().hex}"


def _core_counts(store: CanonicalStore) -> dict[str, int]:
    counts = store.counts()
    result: dict[str, int] = {}
    for table in CANONICAL_IDENTITY_TABLES:
        value = counts.get(table, 0)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Canonical count is invalid")
        result[table] = value
    return result


def _diagnostic_counts(store: CanonicalStore) -> dict[str, int]:
    counts = store.counts()
    result: dict[str, int] = {}
    for table in DIAGNOSTIC_COUNT_TABLES:
        value = counts.get(table, 0)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Canonical count is invalid")
        result[table] = value
    return result


def _known_error(value: object) -> str:
    if not isinstance(value, str):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Run failure code is invalid")
    try:
        return ErrorCode(value).value
    except ValueError as error:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Run failure code is invalid") from error


def _counter(records: list[Mapping[str, Any]], field: str, *, allowed: frozenset[str]) -> dict[str, int]:
    values: Counter[str] = Counter()
    for record in records:
        value = record.get(field)
        if not isinstance(value, str) or value not in allowed:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Diagnostic state is invalid")
        values[value] += 1
    return dict(sorted(values.items()))


def assert_diagnostic_safe(payload: object) -> None:
    """Validate the narrow diagnostic allowlist before persistence or export."""

    def scan(value: object, *, field: str | None = None) -> None:
        if field in _FORBIDDEN_FIELD_NAMES:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Diagnostic payload violated the allowlist")
        if isinstance(value, Mapping):
            if field is None and frozenset(value) not in _ALLOWED_ROOT_FIELD_SETS:
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Diagnostic payload violated the allowlist")
            if len(value) > 256:
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Diagnostic payload exceeded its allowlist")
            for key, nested in value.items():
                if not isinstance(key, str) or not key or len(key) > 80:
                    raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Diagnostic payload violated the allowlist")
                scan(nested, field=key)
            return
        if isinstance(value, (list, tuple)):
            if len(value) > MAX_JOURNAL_EVENTS:
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Diagnostic payload exceeded its allowlist")
            for nested in value:
                scan(nested, field=field)
            return
        if value is None or isinstance(value, bool) or isinstance(value, int):
            return
        if (
            isinstance(value, str)
            and len(value) <= 512
            and not any(pattern.search(value) for pattern in _FORBIDDEN_VALUE_PATTERNS)
        ):
            return
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Diagnostic payload violated the allowlist")

    scan(payload)


@dataclass(frozen=True)
class DiagnosticEvent:
    """Append-only, content-free lifecycle event for a diagnosable operation."""

    event_id: str
    run_id: str
    stage: str
    component: str
    state: Literal["started", "succeeded", "failed", "skipped"]
    error_code: ErrorCode | None
    occurred_at: str
    attempt: int

    def __post_init__(self) -> None:
        if (
            _EVENT_ID.fullmatch(self.event_id) is None
            or _RUN_ID.fullmatch(self.run_id) is None
            or self.stage not in RECOVERY_STAGES
            or self.component not in DIAGNOSTIC_COMPONENTS
            or self.state not in EVENT_STATES
            or (self.error_code is not None and not isinstance(self.error_code, ErrorCode))
            or _RFC3339.fullmatch(self.occurred_at) is None
            or not isinstance(self.attempt, int)
            or isinstance(self.attempt, bool)
            or not 1 <= self.attempt <= 100
        ):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Diagnostic event is invalid")
        if (self.state == "failed") != (self.error_code is not None):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Diagnostic event error state is invalid")

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        stage: str,
        component: str,
        state: Literal["started", "succeeded", "failed", "skipped"],
        error_code: ErrorCode | None = None,
        occurred_at: str | None = None,
        attempt: int = 1,
    ) -> "DiagnosticEvent":
        return cls(
            event_id=f"evt_{uuid.uuid4().hex}",
            run_id=run_id,
            stage=stage,
            component=component,
            state=state,
            error_code=error_code,
            occurred_at=occurred_at or _utc_now(),
            attempt=attempt,
        )

    def safe_dict(self) -> dict[str, Any]:
        payload = {
            "attempt": self.attempt,
            "component": self.component,
            "error_code": None if self.error_code is None else self.error_code.value,
            "event_id": self.event_id,
            "occurred_at": self.occurred_at,
            "run_id": self.run_id,
            "stage": self.stage,
            "state": self.state,
        }
        assert_diagnostic_safe(payload)
        return payload

    @classmethod
    def from_safe_dict(cls, value: object) -> "DiagnosticEvent":
        if not isinstance(value, Mapping) or set(value) != {
            "attempt",
            "component",
            "error_code",
            "event_id",
            "occurred_at",
            "run_id",
            "stage",
            "state",
        }:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Diagnostic journal is invalid")
        raw_code = value.get("error_code")
        try:
            code = None if raw_code is None else ErrorCode(raw_code)
        except ValueError as error:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Diagnostic journal is invalid") from error
        try:
            return cls(
                event_id=str(value["event_id"]),
                run_id=str(value["run_id"]),
                stage=str(value["stage"]),
                component=str(value["component"]),
                state=str(value["state"]),  # type: ignore[arg-type]
                error_code=code,
                occurred_at=str(value["occurred_at"]),
                attempt=value["attempt"],
            )
        except (KeyError, TypeError, X2NRuntimeError) as error:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Diagnostic journal is invalid") from error


class DiagnosticJournal:
    """Owner-private bounded journal which cannot accept free-form diagnostic data."""

    def __init__(self, paths: RuntimePaths) -> None:
        self.paths = paths
        self.path = paths.data_root / "runtime/diagnostics" / JOURNAL_FILENAME

    def _load(self) -> list[DiagnosticEvent]:
        self.paths.ensure_private_file(self.path)
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Diagnostic journal is unreadable") from error
        if not isinstance(raw, Mapping) or set(raw) != {"events", "schema_version"}:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Diagnostic journal is invalid")
        if raw.get("schema_version") != DIAGNOSTIC_SCHEMA_VERSION or not isinstance(raw.get("events"), list):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Diagnostic journal is invalid")
        if len(raw["events"]) > MAX_JOURNAL_EVENTS:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Diagnostic journal is oversized")
        events = [DiagnosticEvent.from_safe_dict(item) for item in raw["events"]]
        assert_diagnostic_safe(
            {"events": [item.safe_dict() for item in events], "schema_version": DIAGNOSTIC_SCHEMA_VERSION}
        )
        return events

    def events(self, *, limit: int = 20) -> tuple[DiagnosticEvent, ...]:
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_JOURNAL_EVENTS:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Diagnostic journal limit is invalid")
        return tuple(self._load()[-limit:])

    def append(self, event: DiagnosticEvent) -> None:
        if not isinstance(event, DiagnosticEvent):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Diagnostic event is invalid")
        events = [*self._load(), event][-MAX_JOURNAL_EVENTS:]
        payload = {
            "events": [item.safe_dict() for item in events],
            "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
        }
        assert_diagnostic_safe(payload)
        _atomic_private_json(self.path, payload)
        self.paths.ensure_private_file(self.path)


def build_local_doctor_probe(
    paths: RuntimePaths,
    *,
    env: Mapping[str, str] | None = None,
) -> DoctorProbe:
    """Collect Boolean and enum-only health facts; never serialize discovered paths."""

    values = os.environ if env is None else env
    try:
        database_health = CanonicalStore(paths).health()
        database_state: Literal["ok", "busy", "failed"] = (
            "ok" if database_health.get("status") == "healthy" else "failed"
        )
    except sqlite3.OperationalError:
        database_state = "busy"
    except Exception:
        database_state = "failed"

    try:
        sessions = SessionHealthStore(paths).evaluate_all()
    except X2NRuntimeError:
        sessions = tuple(
            SessionHealth(
                platform,
                "blocked",
                "session_checkpoint_invalid",
                ErrorCode.DATA_INTEGRITY_FAILED,
                "inspect_diagnostics_and_keep_adapter_disabled",
                False,
            )
            for platform in PROFILE_PLATFORMS
        )
    home_value = values.get("HOME")
    host_registered = bool(home_value and Path(home_value).is_absolute() and native_host_registered(Path(home_value)))
    return DoctorProbe(
        extension_reachable=host_registered,
        native_host_registered=host_registered,
        companion_reachable=True,
        canonical_db_state=database_state,
        ffmpeg_available=ffmpeg_available(),
        provider_configured=safe_reference_configured(values, "X2N_PROVIDER_SECRET_REF"),
        notion_authorized=safe_reference_configured(values, "X2N_NOTION_SECRET_REF"),
        chrome_available=chrome_available(),
        sessions=sessions,
    )


@dataclass(frozen=True)
class StartupRecoveryReceipt:
    """Aggregate-only restart receipt; Canonical rows never enter the receipt."""

    run_id: str
    before: RecoveryPlan
    after: RecoveryPlan
    canonical_before: Mapping[str, int]
    canonical_after: Mapping[str, int]
    artifacts_before: int
    artifacts_after: int
    current_page_resumed: int
    markdown: MarkdownRebuild
    notion_mode: str
    notion_deliveries: Mapping[str, int]

    def safe_dict(self) -> dict[str, Any]:
        payload = {
            "append_only_artifacts": {
                "after": self.artifacts_after,
                "before": self.artifacts_before,
                "decreased": self.artifacts_after < self.artifacts_before,
            },
            "canonical_core_counts": {
                "after": dict(self.canonical_after),
                "before": dict(self.canonical_before),
                "unchanged": self.canonical_before == self.canonical_after,
            },
            "current_page_resumed": self.current_page_resumed,
            "markdown": {
                "category_index_writes": self.markdown.category_index_writes,
                "checked_links": self.markdown.checked_links,
                "content_writes": self.markdown.content_writes,
                "manifest": self.markdown.manifest.safe_dict(),
                "removed_category_indexes": self.markdown.removed_category_indexes,
                "removed_content_files": self.markdown.removed_content_files,
            },
            "notion": {
                "deliveries": dict(sorted(self.notion_deliveries.items())),
                "mode": self.notion_mode,
                "real_transport": "NOT_RUN" if self.notion_mode == "disabled_not_configured" else "CALLER_CONTROLLED",
            },
            "recovery_after": self.after.safe_dict(),
            "recovery_before": self.before.safe_dict(),
            "run_id": self.run_id,
            "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
        }
        assert_diagnostic_safe(payload)
        return payload


class OperationsService:
    """Operational read models and one bounded recovery pass over local authorities."""

    def __init__(self, store: CanonicalStore) -> None:
        self.store = store
        self.journal = DiagnosticJournal(store.paths)

    def doctor(self, *, probe: DoctorProbe | None = None) -> DoctorReport:
        return build_doctor_report(probe or build_local_doctor_probe(self.store.paths))

    def record_stage_outcome(
        self,
        *,
        stage: str,
        state: Literal["succeeded", "failed", "skipped"],
        error_code: ErrorCode | None = None,
        component: str = "pipeline",
        occurred_at: str | None = None,
    ) -> dict[str, Any]:
        """Record a stable, redacted terminal event for a bounded pipeline stage."""

        event = DiagnosticEvent.create(
            run_id=_new_run_id(),
            stage=stage,
            component=component,
            state=state,
            error_code=error_code,
            occurred_at=occurred_at,
        )
        self.journal.append(event)
        return event.safe_dict()

    def recovery_plan(self) -> dict[str, Any]:
        payload = {
            "recovery": self.store.recovery_plan().safe_dict(),
            "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
            "task_id": TASK_ID,
        }
        assert_diagnostic_safe(payload)
        return payload

    def diagnostic_bundle(self, *, probe: DoctorProbe | None = None) -> dict[str, Any]:
        """Build a read-only aggregate bundle from Canonical and the redacted journal."""

        snapshot = self.store.local_ui_snapshot()
        jobs = snapshot.get("jobs")
        outbox = snapshot.get("outbox")
        if not isinstance(jobs, list) or not all(isinstance(item, Mapping) for item in jobs):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Local diagnostic job snapshot is invalid")
        if not isinstance(outbox, list) or not all(isinstance(item, Mapping) for item in outbox):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Local diagnostic outbox snapshot is invalid")
        failed_runs: list[dict[str, str]] = []
        for job in jobs:
            code = job.get("error_code")
            if code is None:
                continue
            job_id = job.get("job_id")
            state = job.get("state")
            if not isinstance(job_id, str) or not isinstance(state, str) or state not in {"failed", "cancelled"}:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Run failure state is invalid")
            failed_runs.append({"error_code": _known_error(code), "run_id": _opaque_run_id(job_id), "state": state})
        report = self.doctor(probe=probe).safe_dict()
        journal_events = [item.safe_dict() for item in self.journal.events(limit=20)]
        payload = {
            "canonical_counts": _diagnostic_counts(self.store),
            "data_lifecycle": {
                "diagnostic_free_text_persisted": 0,
                "media_cdn_urls_emitted": 0,
                "private_paths_emitted": False,
                "raw_media_emitted": 0,
                "secret_values_emitted": 0,
            },
            "doctor": report,
            "journal": {"event_count": len(journal_events), "recent_events": journal_events},
            "metrics": {
                "authority": "derived_from_canonical_store_not_persisted",
                "failed_runs": failed_runs,
                "job_states": _counter(jobs, "state", allowed=RUN_STATES),
                "outbox_states": _counter(outbox, "status", allowed=OUTBOX_STATES),
            },
            "recovery": self.store.recovery_plan().safe_dict(),
            "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
            "task_id": TASK_ID,
        }
        assert_diagnostic_safe(payload)
        return payload

    def _reconcile_notion(
        self,
        worker: NotionSinkWorker | None,
        *,
        now: str,
    ) -> tuple[str, dict[str, int]]:
        if worker is None:
            return "disabled_not_configured", {"not_run": 1}
        if worker.store is not self.store:
            raise X2NRuntimeError(
                ErrorCode.DATA_INTEGRITY_FAILED, "Notion recovery worker does not match Canonical Store"
            )
        deliveries: Counter[str] = Counter()
        for canonical in self.store.projection_snapshots():
            result = worker.reconcile(build_sink_projection(canonical), now=now)
            deliveries[result.state] += 1
        return "explicit_worker", dict(sorted(deliveries.items()))

    def startup_recovery(
        self,
        *,
        now: str | None = None,
        notion_worker: NotionSinkWorker | None = None,
    ) -> StartupRecoveryReceipt:
        """Run one idempotent local recovery pass and fail closed on any divergence.

        The production CLI deliberately leaves ``notion_worker`` unset, so this
        method never creates a real Notion transport by itself.  A caller that
        already owns an explicitly configured worker may inject it; CI uses the
        in-process Notion semantic double only.
        """

        observed_at = now or _utc_now()
        if _RFC3339.fullmatch(observed_at) is None:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Recovery timestamp is invalid")
        run_id = _new_run_id()
        self.journal.append(
            DiagnosticEvent.create(
                run_id=run_id,
                stage="db_commit",
                component="startup_recovery",
                state="started",
                occurred_at=observed_at,
            )
        )
        before_counts = _core_counts(self.store)
        artifacts_before = _diagnostic_counts(self.store)["artifact"]
        before = self.store.recovery_plan(now=observed_at)
        try:
            self.store.apply_recovery(now=observed_at)
            resumed = CurrentPageOrchestrator(self.store).resume_pending()
            if self.store.resumable_current_page_jobs():
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Current-page recovery left a running job")
            markdown = MarkdownSink(self.store).rebuild_from_canonical(build_sink_projection)
            notion_mode, notion_deliveries = self._reconcile_notion(notion_worker, now=observed_at)
            after_counts = _core_counts(self.store)
            artifacts_after = _diagnostic_counts(self.store)["artifact"]
            after = self.store.recovery_plan(now=observed_at)
            if (
                after_counts != before_counts
                or artifacts_after < artifacts_before
                or self.store.health().get("status") != "healthy"
            ):
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Recovery changed Canonical content")
        except X2NRuntimeError as error:
            self.journal.append(
                DiagnosticEvent.create(
                    run_id=run_id,
                    stage="db_commit",
                    component="startup_recovery",
                    state="failed",
                    error_code=error.code,
                    occurred_at=observed_at,
                )
            )
            raise
        except Exception as error:
            self.journal.append(
                DiagnosticEvent.create(
                    run_id=run_id,
                    stage="db_commit",
                    component="startup_recovery",
                    state="failed",
                    error_code=ErrorCode.UNKNOWN_FAILURE,
                    occurred_at=observed_at,
                )
            )
            raise X2NRuntimeError(ErrorCode.UNKNOWN_FAILURE, "Recovery stopped before completion") from error
        self.journal.append(
            DiagnosticEvent.create(
                run_id=run_id,
                stage="db_commit",
                component="startup_recovery",
                state="succeeded",
                occurred_at=observed_at,
            )
        )
        return StartupRecoveryReceipt(
            run_id=run_id,
            before=before,
            after=after,
            canonical_before=before_counts,
            canonical_after=after_counts,
            artifacts_before=artifacts_before,
            artifacts_after=artifacts_after,
            current_page_resumed=len(resumed),
            markdown=markdown,
            notion_mode=notion_mode,
            notion_deliveries=notion_deliveries,
        )
