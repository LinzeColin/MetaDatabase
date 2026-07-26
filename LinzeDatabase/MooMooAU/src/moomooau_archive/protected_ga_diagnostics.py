"""Closed, public-safe diagnostics for one protected GA rehearsal.

The tracker stores only fixed enums.  It never receives an exception, URL, identifier,
counter, Secret, mailbox field, repository locator, or message-derived value.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .github_guard import InstallationTokenFailureClass

FAILURE_TAXONOMY_VERSION = "moomooau.protected-ga-failure-taxonomy.v1"


class ProtectedGAFailurePhase(StrEnum):
    """Closed operation phases that are safe to expose after a failed attempt."""

    ENTRYPOINT = "ENTRYPOINT"
    CONTEXT_GATE = "CONTEXT_GATE"
    PREDECESSOR_BINDING = "PREDECESSOR_BINDING"
    FAILED_ATTEMPT_BINDING = "FAILED_ATTEMPT_BINDING"
    RUN_CONTRACT = "RUN_CONTRACT"
    CONFIG_CAPACITY = "CONFIG_CAPACITY"
    PROCESSING_REGISTRIES = "PROCESSING_REGISTRIES"
    GITHUB_APP_KEY = "GITHUB_APP_KEY"
    AGE_IDENTITY = "AGE_IDENTITY"
    GITHUB_APP_TOKEN = "GITHUB_APP_TOKEN"
    REPOSITORY_RESOLUTION = "REPOSITORY_RESOLUTION"
    LIVE_CAPACITY_REFRESH = "LIVE_CAPACITY_REFRESH"
    GMAIL_OAUTH = "GMAIL_OAUTH"
    SCHEDULE_CHECKPOINT_RECOVERY = "SCHEDULE_CHECKPOINT_RECOVERY"
    SCHEDULE_PLANNING = "SCHEDULE_PLANNING"
    RUNTIME_PREFLIGHT = "RUNTIME_PREFLIGHT"
    CHECKPOINT_RECOVERY = "CHECKPOINT_RECOVERY"
    MAILBOX_RECONCILIATION = "MAILBOX_RECONCILIATION"
    PRIOR_TIMELINE_RECOVERY = "PRIOR_TIMELINE_RECOVERY"
    METADATA_VERIFICATION = "METADATA_VERIFICATION"
    RAW_FETCH = "RAW_FETCH"
    RAW_ENCRYPTION_PLAN = "RAW_ENCRYPTION_PLAN"
    RAW_COMMIT = "RAW_COMMIT"
    RAW_RECOVERY = "RAW_RECOVERY"
    PROCESSED_PLAN = "PROCESSED_PLAN"
    PROCESSED_COMMIT = "PROCESSED_COMMIT"
    FULL_RECOVERY = "FULL_RECOVERY"
    SECOND_VERIFICATION = "SECOND_VERIFICATION"
    TRASH_MUTATION = "TRASH_MUTATION"
    CURRENT_POINTER_RECOVERY = "CURRENT_POINTER_RECOVERY"
    TIMELINE_EVENT = "TIMELINE_EVENT"
    TIMELINE_SNAPSHOT_PLAN = "TIMELINE_SNAPSHOT_PLAN"
    TIMELINE_SNAPSHOT_COMMIT = "TIMELINE_SNAPSHOT_COMMIT"
    TIMELINE_SNAPSHOT_RECOVERY = "TIMELINE_SNAPSHOT_RECOVERY"
    TIMELINE_PUBLISH = "TIMELINE_PUBLISH"
    CHECKPOINT_COMMIT = "CHECKPOINT_COMMIT"
    AGGREGATE_GATE = "AGGREGATE_GATE"
    RESOURCE_CLEANUP = "RESOURCE_CLEANUP"

    @property
    def reason_code(self) -> str:
        return f"PROTECTED_GA_{self.value}_FAILED"


@dataclass(slots=True, repr=False)
class ProtectedGADiagnostics:
    """Retain only the latest closed-enum phase and token failure class."""

    _phase: ProtectedGAFailurePhase = ProtectedGAFailurePhase.ENTRYPOINT
    _installation_token_failure_class: InstallationTokenFailureClass = (
        InstallationTokenFailureClass.UNCLASSIFIED
    )

    @property
    def phase(self) -> ProtectedGAFailurePhase:
        return self._phase

    @property
    def installation_token_failure_class(self) -> InstallationTokenFailureClass:
        return self._installation_token_failure_class

    def enter(self, phase: ProtectedGAFailurePhase) -> None:
        if not isinstance(phase, ProtectedGAFailurePhase):
            raise TypeError("protected GA diagnostic phase is invalid")
        self._phase = phase
        self._installation_token_failure_class = InstallationTokenFailureClass.UNCLASSIFIED

    def enter_installation_token_failure(
        self,
        failure_class: InstallationTokenFailureClass,
    ) -> None:
        if not isinstance(failure_class, InstallationTokenFailureClass):
            raise TypeError("installation token failure class is invalid")
        self._phase = ProtectedGAFailurePhase.GITHUB_APP_TOKEN
        self._installation_token_failure_class = failure_class

    def __repr__(self) -> str:
        return "ProtectedGADiagnostics(phase=<public-safe-enum>)"


def public_failure_payload(diagnostics: ProtectedGADiagnostics) -> dict[str, object]:
    """Render a fixed failure object without inspecting the triggering exception."""

    if not isinstance(diagnostics, ProtectedGADiagnostics):
        raise TypeError("protected GA diagnostics are invalid")
    phase = diagnostics.phase
    return {
        "schema_version": "moomooau.protected-ga-public-failure.v1",
        "status": "BLOCKED",
        "reason_code": phase.reason_code,
        "failure_phase": phase.value,
        "installation_token_failure_class": (diagnostics.installation_token_failure_class.value),
        "diagnostic_taxonomy": FAILURE_TAXONOMY_VERSION,
        "exact_root_cause_claimed": False,
        "protected_values_disclosed": False,
        "platform_schedule_event_claimed": False,
        "production_health_claimed": False,
        "final_acceptance_claimed": False,
    }
