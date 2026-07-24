"""Private-first publication and exact-message mutation state machine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PublicationSagaError(RuntimeError):
    """A private-first transition would create false public or mutation state."""


class PrivateState(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    RECOVERY_VERIFIED = "RECOVERY_VERIFIED"
    FAILED = "FAILED"


class PublicState(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    VERIFIED = "VERIFIED"
    PENDING_RECONCILIATION = "PENDING_RECONCILIATION"


class SourceMutationState(StrEnum):
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    CONFIRMED = "CONFIRMED"
    UNKNOWN = "UNKNOWN"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class PublicationSagaSnapshot:
    private_state: PrivateState
    public_state: PublicState
    source_mutation_state: SourceMutationState
    private_attempts: int
    public_attempts: int
    source_mutation_attempts: int

    @property
    def public_success_claimed(self) -> bool:
        return self.public_state is PublicState.VERIFIED

    @property
    def m3_authorized(self) -> bool:
        return self.private_state is PrivateState.RECOVERY_VERIFIED


class PrivateFirstPublicationSaga:
    """Bind public truth and M3 authority to a verified private recovery."""

    def __init__(self) -> None:
        self._private = PrivateState.NOT_STARTED
        self._public = PublicState.NOT_STARTED
        self._mutation = SourceMutationState.NOT_ATTEMPTED
        self._private_attempts = 0
        self._public_attempts = 0
        self._mutation_attempts = 0

    @property
    def snapshot(self) -> PublicationSagaSnapshot:
        return PublicationSagaSnapshot(
            self._private,
            self._public,
            self._mutation,
            self._private_attempts,
            self._public_attempts,
            self._mutation_attempts,
        )

    def record_private(self, *, committed: bool, recovery_verified: bool) -> None:
        if self._private is not PrivateState.NOT_STARTED:
            raise PublicationSagaError("private outcome is immutable within a run")
        self._private_attempts += 1
        self._private = (
            PrivateState.RECOVERY_VERIFIED
            if committed and recovery_verified
            else PrivateState.FAILED
        )

    def record_public(self, *, remote_verified: bool) -> None:
        if self._private is not PrivateState.RECOVERY_VERIFIED:
            raise PublicationSagaError("public publication requires private recovery")
        if self._public is PublicState.VERIFIED:
            raise PublicationSagaError("verified public state cannot be republished")
        self._public_attempts += 1
        self._public = (
            PublicState.VERIFIED if remote_verified else PublicState.PENDING_RECONCILIATION
        )

    def reconcile_public(self, *, remote_verified: bool) -> None:
        if self._public is not PublicState.PENDING_RECONCILIATION:
            raise PublicationSagaError("only pending public state may be reconciled")
        self._public_attempts += 1
        if remote_verified:
            self._public = PublicState.VERIFIED

    def record_source_mutation(self, *, confirmed: bool, outcome_known: bool = True) -> None:
        if self._private is not PrivateState.RECOVERY_VERIFIED:
            raise PublicationSagaError("M3 requires private recovery")
        if self._mutation is not SourceMutationState.NOT_ATTEMPTED:
            raise PublicationSagaError(
                "an uncertain or completed M3 must be reconciled, not repeated"
            )
        self._mutation_attempts += 1
        if not outcome_known:
            self._mutation = SourceMutationState.UNKNOWN
        elif confirmed:
            self._mutation = SourceMutationState.CONFIRMED
        else:
            self._mutation = SourceMutationState.FAILED
