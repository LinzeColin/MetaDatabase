"""Closed, public-safe diagnostics for a protected M3 Budget-1 attempt.

The tracker stores only a fixed enum.  It never receives an exception, URL, identifier,
counter, Secret, mailbox field, repository locator, or message-derived value.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

FAILURE_TAXONOMY_VERSION = "moomooau.protected-m3-failure-taxonomy.v1"


class ProtectedM3FailurePhase(StrEnum):
    """Closed operation phases that are safe to expose after a failed attempt."""

    ENTRYPOINT = "ENTRYPOINT"
    CONTEXT_GATE = "CONTEXT_GATE"
    BETA_BINDING = "BETA_BINDING"
    PRIOR_ATTEMPT_BINDING = "PRIOR_ATTEMPT_BINDING"
    RUN_CONTRACT = "RUN_CONTRACT"
    CONFIG_CAPACITY = "CONFIG_CAPACITY"
    PROCESSING_REGISTRIES = "PROCESSING_REGISTRIES"
    GITHUB_APP_KEY = "GITHUB_APP_KEY"
    AGE_IDENTITY = "AGE_IDENTITY"
    GMAIL_OAUTH = "GMAIL_OAUTH"
    GITHUB_APP_TOKEN = "GITHUB_APP_TOKEN"
    REPOSITORY_RESOLUTION = "REPOSITORY_RESOLUTION"
    RUNTIME_PREFLIGHT = "RUNTIME_PREFLIGHT"
    MAILBOX_DISCOVERY = "MAILBOX_DISCOVERY"
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
    AGGREGATE_GATE = "AGGREGATE_GATE"
    RESOURCE_CLEANUP = "RESOURCE_CLEANUP"

    @property
    def reason_code(self) -> str:
        return f"PROTECTED_M3_{self.value}_FAILED"


@dataclass(slots=True, repr=False)
class ProtectedM3Diagnostics:
    """Retain only the latest closed-enum operation phase."""

    _phase: ProtectedM3FailurePhase = ProtectedM3FailurePhase.ENTRYPOINT

    @property
    def phase(self) -> ProtectedM3FailurePhase:
        return self._phase

    def enter(self, phase: ProtectedM3FailurePhase) -> None:
        if not isinstance(phase, ProtectedM3FailurePhase):
            raise TypeError("protected M3 diagnostic phase is invalid")
        self._phase = phase

    def __repr__(self) -> str:
        return "ProtectedM3Diagnostics(phase=<public-safe-enum>)"


def public_failure_payload(diagnostics: ProtectedM3Diagnostics) -> dict[str, object]:
    """Render a fixed failure object without inspecting the triggering exception."""

    if not isinstance(diagnostics, ProtectedM3Diagnostics):
        raise TypeError("protected M3 diagnostics are invalid")
    phase = diagnostics.phase
    return {
        "schema_version": "moomooau.protected-m3-execution.v1",
        "status": "BLOCKED",
        "reason_code": phase.reason_code,
        "failure_phase": phase.value,
        "diagnostic_taxonomy": FAILURE_TAXONOMY_VERSION,
        "exact_root_cause_claimed": False,
        "production_health_claimed": False,
        "final_acceptance_claimed": False,
    }
