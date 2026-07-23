"""Public-safe, fixed diagnostics for the protected Raw-only Beta entrypoint.

The tracker accepts only a closed enum and never receives an exception, URL, identifier,
counter, Secret, or message-derived value.  It therefore narrows a protected failure to one
bounded operation phase without turning public workflow output into a data-exfiltration path.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

FAILURE_TAXONOMY_VERSION = "moomooau.protected-beta-failure-taxonomy.v1"


class ProtectedBetaFailurePhase(StrEnum):
    """Closed public-safe phases for a failed protected Beta attempt."""

    ENTRYPOINT = "ENTRYPOINT"
    CONTEXT_GATE = "CONTEXT_GATE"
    ALPHA_BINDING = "ALPHA_BINDING"
    CONFIG_CAPACITY = "CONFIG_CAPACITY"
    SENDER_REGISTRY = "SENDER_REGISTRY"
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
    REMOTE_RECOVERY = "REMOTE_RECOVERY"
    AGGREGATE_GATE = "AGGREGATE_GATE"
    RESOURCE_CLEANUP = "RESOURCE_CLEANUP"

    @property
    def reason_code(self) -> str:
        return f"PROTECTED_BETA_{self.value}_FAILED"


@dataclass(slots=True, repr=False)
class ProtectedBetaDiagnostics:
    """Retain only the latest closed-enum operation phase."""

    _phase: ProtectedBetaFailurePhase = ProtectedBetaFailurePhase.ENTRYPOINT

    @property
    def phase(self) -> ProtectedBetaFailurePhase:
        return self._phase

    def enter(self, phase: ProtectedBetaFailurePhase) -> None:
        if not isinstance(phase, ProtectedBetaFailurePhase):
            raise TypeError("protected Beta diagnostic phase is invalid")
        self._phase = phase

    def __repr__(self) -> str:
        return "ProtectedBetaDiagnostics(phase=<public-safe-enum>)"


def failure_reason_codes() -> tuple[str, ...]:
    """Return the complete immutable reason-code vocabulary."""

    return tuple(phase.reason_code for phase in ProtectedBetaFailurePhase)


def public_failure_payload(diagnostics: ProtectedBetaDiagnostics) -> dict[str, object]:
    """Render an exact failure object without inspecting the triggering exception."""

    if not isinstance(diagnostics, ProtectedBetaDiagnostics):
        raise TypeError("protected Beta diagnostics are invalid")
    phase = diagnostics.phase
    return {
        "schema_version": "moomooau.protected-beta-execution.v1",
        "status": "BLOCKED",
        "reason_code": phase.reason_code,
        "failure_phase": phase.value,
        "diagnostic_taxonomy": FAILURE_TAXONOMY_VERSION,
        "exact_root_cause_claimed": False,
        "production_health_claimed": False,
        "final_acceptance_claimed": False,
    }
