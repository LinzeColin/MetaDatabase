"""Codex development and monitoring boundaries; no model participates in the data plane."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import cast

from .public_inventory import PublicInventoryDocument


class ModelBoundaryError(RuntimeError):
    pass


class DevelopmentInputKind(StrEnum):
    FROZEN_TASKPACK = "FROZEN_TASKPACK"
    PUBLIC_CODE = "PUBLIC_CODE"
    SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"
    PUBLIC_EVIDENCE = "PUBLIC_EVIDENCE"
    REAL_EMAIL = "REAL_EMAIL"
    PRIVATE_OBJECT = "PRIVATE_OBJECT"
    SECRET = "SECRET"  # pragma: allowlist secret


class RequestedCapability(StrEnum):
    READ_PUBLIC_CODE = "READ_PUBLIC_CODE"
    FIX_PUBLIC_CODE = "FIX_PUBLIC_CODE"
    READ_REAL_EMAIL = "READ_REAL_EMAIL"
    PRINT_RECOVERY_SECRET = "PRINT_RECOVERY_SECRET"  # pragma: allowlist secret
    THREAD_TRASH = "THREAD_TRASH"
    CREATE_SECOND_PRIVATE_REPOSITORY = "CREATE_SECOND_PRIVATE_REPOSITORY"
    INSTALL_LOCAL_SCHEDULER = "INSTALL_LOCAL_SCHEDULER"
    TRIGGER_PRODUCTION = "TRIGGER_PRODUCTION"
    PUBLISH_SENSITIVE_EVIDENCE = "PUBLISH_SENSITIVE_EVIDENCE"
    SKIP_ORACLE = "SKIP_ORACLE"


class BoundaryDecision(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class AutoAction(StrEnum):
    NONE = "NONE"
    UPDATE_SINGLE_OPS_ISSUE = "UPDATE_SINGLE_OPS_ISSUE"
    DISABLED = "DISABLED"


_AUTO_EVIDENCE_PATH = "LinzeDatabase/MooMooAU/evidence/ops/latest.json"
_AUTO_THREAD_PROMPT = (
    "Inspect the referenced public MooMooAU health evidence in the Codex development thread."
)


_ALLOWED_INPUTS = {
    DevelopmentInputKind.FROZEN_TASKPACK,
    DevelopmentInputKind.PUBLIC_CODE,
    DevelopmentInputKind.SYNTHETIC_FIXTURE,
    DevelopmentInputKind.PUBLIC_EVIDENCE,
}
_ALLOWED_CAPABILITIES = {
    RequestedCapability.READ_PUBLIC_CODE,
    RequestedCapability.FIX_PUBLIC_CODE,
}


class CodexDevelopmentBoundary:
    """Describe the external development policy; runtime exposes no model dispatch port."""

    def authorize_input(self, input_kind: DevelopmentInputKind) -> BoundaryDecision:
        return BoundaryDecision.ALLOW if input_kind in _ALLOWED_INPUTS else BoundaryDecision.DENY

    def decide(self, capability: RequestedCapability) -> BoundaryDecision:
        return (
            BoundaryDecision.ALLOW if capability in _ALLOWED_CAPABILITIES else BoundaryDecision.DENY
        )


@dataclass(frozen=True, slots=True)
class PassiveCodexAutoContract:
    """Exact noncritical authority envelope for the owner-created ordinary Automation."""

    name: str = "MooMooAU passive health check"
    schedule_frequency: str = "DAILY"
    schedule_target: str = "04:30"
    timezone: str = "Australia/Sydney"
    public_repository: str = "LinzeColin/MetaDatabase"
    public_evidence_path: str = _AUTO_EVIDENCE_PATH
    maximum_evidence_age: timedelta = timedelta(hours=48)
    issue_label: str = "moomooau-ops"
    maximum_issue_updates: int = 1
    gmail_reads_allowed: bool = False
    private_repository_reads_allowed: bool = False
    secret_reads_allowed: bool = False
    encrypted_data_reads_allowed: bool = False
    workflow_dispatches_allowed: bool = False
    code_writes_allowed: bool = False
    conversation_continuations_allowed: bool = False
    data_plane_dependency: bool = False

    def __post_init__(self) -> None:
        exact_values = (
            self.name == "MooMooAU passive health check",
            self.schedule_frequency == "DAILY",
            self.schedule_target == "04:30",
            self.timezone == "Australia/Sydney",
            self.public_repository == "LinzeColin/MetaDatabase",
            self.public_evidence_path == _AUTO_EVIDENCE_PATH,
            self.maximum_evidence_age == timedelta(hours=48),
            self.issue_label == "moomooau-ops",
            self.maximum_issue_updates == 1,
        )
        forbidden_authority = (
            self.gmail_reads_allowed,
            self.private_repository_reads_allowed,
            self.secret_reads_allowed,
            self.encrypted_data_reads_allowed,
            self.workflow_dispatches_allowed,
            self.code_writes_allowed,
            self.conversation_continuations_allowed,
            self.data_plane_dependency,
        )
        if (
            not all(exact_values)
            or type(self.maximum_issue_updates) is not int
            or not all(type(value) is bool for value in forbidden_authority)
            or any(forbidden_authority)
        ):
            raise ModelBoundaryError("Codex Auto contract exceeds the frozen passive boundary")


PASSIVE_CODEX_AUTO_CONTRACT = PassiveCodexAutoContract()


@dataclass(frozen=True, slots=True, repr=False)
class PublicHealthObservation:
    """One strict public inventory plus public commit freshness metadata."""

    document: PublicInventoryDocument
    public_evidence_path: str
    public_commit_at_utc: datetime

    def __post_init__(self) -> None:
        if (
            not isinstance(self.document, PublicInventoryDocument)
            or not _valid_auto_evidence_path(self.public_evidence_path)
            or not _is_utc(self.public_commit_at_utc)
        ):
            raise ModelBoundaryError("public health observation is outside the passive boundary")

    def __repr__(self) -> str:
        return (
            "PublicHealthObservation(document=<redacted-public-document>, "
            f"public_evidence_path={self.public_evidence_path!r}, "
            f"public_commit_at_utc={self.public_commit_at_utc.isoformat()!r})"
        )


@dataclass(frozen=True, slots=True)
class AutoPlan:
    action: AutoAction
    issue_updates: int
    reason_code: str
    issue_label: str | None = None
    public_evidence_path: str | None = None
    development_thread_prompt: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.action, AutoAction) or type(self.reason_code) is not str:
            raise ModelBoundaryError("Codex Auto plan is invalid")
        updates_issue = self.action is AutoAction.UPDATE_SINGLE_OPS_ISSUE
        valid_reason = {
            AutoAction.NONE: {"PUBLIC_HEALTHY_FRESH_NO_ACTION"},
            AutoAction.UPDATE_SINGLE_OPS_ISSUE: {
                "PUBLIC_HEALTH_STALE_SINGLE_ISSUE_BUDGET",
                "PUBLIC_ABNORMAL_SINGLE_ISSUE_BUDGET",
                "PUBLIC_ABNORMAL_AND_STALE_SINGLE_ISSUE_BUDGET",
            },
            AutoAction.DISABLED: {"AUTO_DISABLED_DATA_PLANE_INDEPENDENT"},
        }
        has_exact_issue_target = (
            self.issue_label == PASSIVE_CODEX_AUTO_CONTRACT.issue_label
            and _valid_auto_evidence_path(self.public_evidence_path)
            and self.development_thread_prompt == _AUTO_THREAD_PROMPT
        )
        if (
            type(self.issue_updates) is not int
            or self.issue_updates not in {0, 1}
            or self.reason_code not in valid_reason[self.action]
            or updates_issue != (self.issue_updates == 1)
            or updates_issue != has_exact_issue_target
        ):
            raise ModelBoundaryError("Codex Auto plan is invalid")

    def to_public_dict(self) -> dict[str, object]:
        return {
            "schema_version": "moomooau.codex-auto-plan-public.v1",
            "action": self.action.value,
            "issue_updates": self.issue_updates,
            "reason_code": self.reason_code,
            "public_repository": PASSIVE_CODEX_AUTO_CONTRACT.public_repository,
            "issue_label": self.issue_label,
            "public_evidence_path": self.public_evidence_path,
            "development_thread_prompt": self.development_thread_prompt,
            "gmail_reads": 0,
            "private_repository_reads": 0,
            "secret_reads": 0,
            "encrypted_data_reads": 0,
            "workflow_dispatches": 0,
            "code_writes": 0,
            "conversation_continuations": 0,
            "data_plane_dependency": False,
        }


class CodexAutoMonitor:
    """Read one already-redacted document; never trigger the production workflow."""

    def plan(
        self,
        observation: PublicHealthObservation,
        *,
        now_utc: datetime,
        enabled: bool = True,
    ) -> AutoPlan:
        if not isinstance(observation, PublicHealthObservation) or type(enabled) is not bool:
            raise ModelBoundaryError("Codex Auto input is invalid")
        if not enabled:
            return AutoPlan(AutoAction.DISABLED, 0, "AUTO_DISABLED_DATA_PLANE_INDEPENDENT")
        if not _is_utc(now_utc) or observation.public_commit_at_utc > now_utc:
            raise ModelBoundaryError("public health freshness metadata is invalid")
        try:
            value = json.loads(observation.document.payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ModelBoundaryError("public health evidence is invalid") from exc
        if (
            not isinstance(value, dict)
            or set(value) != {"schema_version", "opaque_root", "run", "datasets"}
            or value.get("schema_version") != "moomooau.public-inventory.v1"
            or value.get("opaque_root") != observation.document.opaque_root
            or not isinstance(value.get("datasets"), list)
            or len(value["datasets"]) != observation.document.dataset_count
            or not isinstance(value.get("run"), dict)
        ):
            raise ModelBoundaryError("public health evidence shape is invalid")
        run = cast(dict[str, object], value["run"])
        healthy = (
            run.get("state") == "HEALTHY"
            and run.get("test_conclusion") == "PASS"
            and run.get("recovery_conclusion") == "PASS"
            and run.get("next_action") == "NONE"
        )
        stale = (
            now_utc - observation.public_commit_at_utc
            > PASSIVE_CODEX_AUTO_CONTRACT.maximum_evidence_age
        )
        if healthy and not stale:
            return AutoPlan(AutoAction.NONE, 0, "PUBLIC_HEALTHY_FRESH_NO_ACTION")
        return AutoPlan(
            AutoAction.UPDATE_SINGLE_OPS_ISSUE,
            1,
            _auto_failure_reason(healthy=healthy, stale=stale),
            issue_label=PASSIVE_CODEX_AUTO_CONTRACT.issue_label,
            public_evidence_path=observation.public_evidence_path,
            development_thread_prompt=_AUTO_THREAD_PROMPT,
        )


def _valid_auto_evidence_path(value: object) -> bool:
    return type(value) is str and value == _AUTO_EVIDENCE_PATH


def _auto_failure_reason(*, healthy: bool, stale: bool) -> str:
    if stale and not healthy:
        return "PUBLIC_ABNORMAL_AND_STALE_SINGLE_ISSUE_BUDGET"
    if stale:
        return "PUBLIC_HEALTH_STALE_SINGLE_ISSUE_BUDGET"
    return "PUBLIC_ABNORMAL_SINGLE_ISSUE_BUDGET"


def _is_utc(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() == timedelta(0)
    )
